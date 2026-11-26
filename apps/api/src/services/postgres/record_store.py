from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import override

from sqlalchemy import (
    ColumnElement,
    Row,
    Select,
    Table,
    Text,
    cast,
    delete,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningDelete

from db.models import LinkModel, RecordModel
from db.names import CommonColumn, LinkColumn, RecordColumn
from services import JsonValue, Link, Record, RecordLinkedError, RecordStore, Tx
from services.postgres.shared import Conditions, Statements
from services.postgres.transaction import get_batches, get_transaction
from services.records import ERROR_STILL_LINKED


class PgRecordStore(RecordStore):
    """Postgres-based ``RecordStore``.

    Links are rows of ``record_links`` with foreign keys: ``ON DELETE CASCADE`` on source, ``RESTRICT`` on target.
    A linked record cannot be deleted.
    """

    COLUMNS: tuple[str, ...] = (
        CommonColumn.ID,
        RecordColumn.CLS,
        RecordColumn.GRAPH,
        RecordColumn.INPUT,
        RecordColumn.ONTOLOGY_VERSION,
        RecordColumn.REVIEW,
    )

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        identity_property_names: Mapping[str, Sequence[str]] | None = None,
    ):
        """
        Args:
            sessions: opens a session for calls without ``tx``.
            identity_property_names: record class -> names of its identity properties.
        """
        self.sessions: async_sessionmaker[AsyncSession] = sessions
        self.table: Table = RecordModel.get_table()
        self.links: Table = LinkModel.get_table()
        self.identity_property_names: dict[str, list[str]] = {
            cls: list(prop_names)
            for cls, prop_names in (identity_property_names or {}).items()
        }

    @override
    async def save_records(
        self, records: Sequence[Record], tx: Tx | None = None
    ) -> None:
        if not records:
            return
        async with get_transaction(self.sessions, tx) as session:
            await session.execute(
                self._build_upsert(), [self._to_row(rec) for rec in records]
            )
            await self._replace_links(session, records)

    @override
    async def get_record(self, record_id: str, tx: Tx | None = None) -> Record | None:
        async with get_transaction(self.sessions, tx) as session:
            found: list[Record] = await self._fetch_records(
                session, RecordModel.id == record_id
            )
        return found[0] if found else None

    @override
    async def delete_record(self, record_id: str, tx: Tx | None = None) -> bool:
        async with get_transaction(self.sessions, tx) as session:
            linking_ids: list[str] = await self._get_linking_ids(session, record_id)
            if linking_ids:
                raise RecordLinkedError(
                    ERROR_STILL_LINKED.format(
                        record_id=record_id, linking_ids=linking_ids
                    )
                )

            # delete outgoing links, including self links
            own_links_condition: ColumnElement[bool] = LinkModel.record_id == record_id
            await session.execute(delete(self.links).where(own_links_condition))

            # delete record row
            deleted: ReturningDelete[str] = (
                delete(self.table)
                .where(RecordModel.id == record_id)
                .returning(RecordModel.id)
            )
            return (await session.execute(deleted)).first() is not None

    @override
    async def get_all_records(self, tx: Tx | None = None) -> list[Record]:
        async with get_transaction(self.sessions, tx) as session:
            return await self._fetch_records(session)

    @override
    async def query_records(
        self,
        query: str,
        cls: str | None = None,
        limit: int | None = None,
        tx: Tx | None = None,
    ) -> list[tuple[Record, float]]:
        graph_text: ColumnElement[str] = cast(RecordModel.graph, Text)
        similarity: ColumnElement[float] = func.similarity(graph_text, query)
        condition: ColumnElement[bool] = similarity > 0

        async with get_transaction(self.sessions, tx) as session:
            if cls is not None:
                return await self._fetch_records_by_similarity(
                    session,
                    RecordModel.cls == cls,
                    condition,
                    order=similarity,
                    limit=limit,
                )
            return await self._fetch_records_by_similarity(
                session, condition, order=similarity, limit=limit
            )

    async def _fetch_records_by_similarity(
        self,
        session: Tx,
        *conditions: ColumnElement[bool],
        order: ColumnElement[float],
        limit: int | None = None,
    ) -> list[tuple[Record, float]]:
        stmt: Select[RecordModel, float] = Statements.overwrite_loaded(
            select(RecordModel, order.label("similarity"))
            .where(*conditions)
            .order_by(order.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows: Sequence[Row[RecordModel, float]] = (await session.execute(stmt)).all()
        records: list[Record] = await self._rows_to_records(
            session, [row_model for row_model, _ in rows]
        )
        return [(record, similarity) for (_, similarity), record in zip(rows, records)]

    @override
    async def get_records(
        self, record_ids: Sequence[str], tx: Tx | None = None
    ) -> list[Record]:
        found: list[Record] = []
        async with get_transaction(self.sessions, tx) as session:
            for batch in get_batches(list(record_ids)):
                found += await self._fetch_records(
                    session, Conditions.match_any(RecordModel.id, batch)
                )
        return found

    @override
    @asynccontextmanager
    async def open_transaction(self, tx: Tx | None = None) -> AsyncGenerator[Tx]:
        async with get_transaction(self.sessions, tx) as session:
            yield session

    @override
    async def get_ontology_versions(self, tx: Tx | None = None) -> dict[str, int]:
        stmt: Select[str, int] = select(
            RecordModel.ontology_version, func.count()
        ).group_by(RecordModel.ontology_version)
        async with get_transaction(self.sessions, tx) as session:
            return {v: count for v, count in (await session.execute(stmt)).all()}

    @override
    async def get_linking_records(
        self, target_ids: Sequence[str], tx: Tx | None = None
    ) -> list[Record]:
        found: dict[str, Record] = {}
        async with get_transaction(self.sessions, tx) as session:
            for batch in get_batches(list(target_ids)):
                linking_id_query: Select[str] = select(LinkModel.record_id).where(
                    Conditions.match_any(LinkModel.target_id, batch)
                )
                records: list[Record] = await self._fetch_records(
                    session, RecordModel.id.in_(linking_id_query)
                )
                found.update((rec.id, rec) for rec in records)
        return [found[rec_id] for rec_id in sorted(found)]

    @override
    async def get_records_to_review(self, tx: Tx | None = None) -> list[Record]:
        async with get_transaction(self.sessions, tx) as session:
            return await self._fetch_records(session, RecordModel.review != "")

    @override
    async def get_records_by_class(
        self, cls: str, tx: Tx | None = None
    ) -> list[Record]:
        async with get_transaction(self.sessions, tx) as session:
            return await self._fetch_records(session, RecordModel.cls == cls)

    @override
    async def lock_record(self, record_id: str, tx: Tx) -> str | None:
        stmt: Select[str] = (
            select(RecordModel.version)
            .where(RecordModel.id == record_id)
            .with_for_update()
        )
        async with get_transaction(self.sessions, tx) as session:
            return await session.scalar(stmt)

    @override
    async def find_record_ids(
        self, cls: str, text: str, tx: Tx | None = None
    ) -> list[str]:
        stmt: Select[str] = (
            select(RecordModel.id)
            .where(
                RecordModel.cls == cls,
                RecordModel.identity_values.contains([text.casefold()]),
            )
            .order_by(RecordModel.id)
        )
        async with get_transaction(self.sessions, tx) as session:
            return list(await session.scalars(stmt))

    def _build_upsert(self) -> Insert:
        """Returns an update-or-insert action."""
        stmt: Insert = insert(self.table)
        replaced: dict[str, ColumnElement[object]] = {
            col: stmt.excluded[col]
            for col in (*self.COLUMNS, RecordColumn.IDENTITY_VALUES)
            if col != CommonColumn.ID
        }
        return stmt.on_conflict_do_update(
            index_elements=[RecordModel.id],
            set_={**replaced, RecordColumn.UPDATED_AT: func.now()},
        )

    def _to_row(self, record: Record) -> dict[str, object]:
        return {
            CommonColumn.ID: record.id,
            RecordColumn.CLS: record.cls,
            RecordColumn.GRAPH: record.graph,
            RecordColumn.INPUT: record.input,
            RecordColumn.ONTOLOGY_VERSION: record.ontology_version,
            RecordColumn.REVIEW: record.review,
            RecordColumn.IDENTITY_VALUES: self._get_identity_values(record),
        }

    def _get_identity_values(self, record: Record) -> list[str]:
        """Returns the id of ``record`` and its identity values, items of lists included, case folded. ``find_record_ids`` looks them up."""
        values: list[str] = [record.id.casefold()]
        for prop_name in self.identity_property_names.get(record.cls, []):
            value: JsonValue = record.graph.get(prop_name)
            items: list[JsonValue] = value if isinstance(value, list) else [value]
            values += [str(item).casefold() for item in items if item is not None]
        return list(dict.fromkeys(values))

    async def _replace_links(self, session: Tx, records: Sequence[Record]) -> None:
        """Updates links of ``records``, in link order. ``records`` may be thousands."""
        # delete old links
        await Statements.delete_matching(
            session, self.links, LinkModel.record_id, [rec.id for rec in records]
        )

        # insert new links
        rows: list[dict[str, object]] = self._to_link_rows(records)
        if rows:
            await session.execute(Statements.build_unnest_insert(self.links, rows))

    @staticmethod
    def _to_link_rows(records: Sequence[Record]) -> list[dict[str, object]]:
        """Returns one row per record link. ``position`` keeps their order."""
        return [
            {
                CommonColumn.RECORD_ID: rec.id,
                CommonColumn.POSITION: position,
                LinkColumn.PROPERTY_NAME: link.property_name,
                LinkColumn.TARGET_ID: link.target_id,
            }
            for rec in records
            for position, link in enumerate(rec.links)
        ]

    async def _get_linking_ids(self, session: Tx, record_id: str) -> list[str]:
        """Returns sorted ids of records that link to ``record_id``, excluding ``record_id``."""
        stmt: Select[str] = select(LinkModel.record_id).where(
            LinkModel.target_id == record_id,
            LinkModel.record_id != record_id,
        )
        return sorted(set(await session.scalars(stmt)))

    def _select_records(self) -> Select[RecordModel]:
        """Returns select statement for all record columns, sorted by id."""
        return Statements.overwrite_loaded(select(RecordModel).order_by(RecordModel.id))

    async def _fetch_records(
        self, session: Tx, *conditions: ColumnElement[bool]
    ) -> list[Record]:
        """Returns records matching all ``conditions`` sorted by id. Returns all records if ``conditions`` is empty."""
        stmt: Select[RecordModel] = self._select_records().where(*conditions)
        rows: Sequence[RecordModel] = (await session.scalars(stmt)).all()
        return await self._rows_to_records(session, rows)

    async def _rows_to_records(
        self, session: Tx, rows: Sequence[RecordModel]
    ) -> list[Record]:
        """Converts rows to records with their links."""
        record_ids: list[str] = [row.id for row in rows]
        links: dict[str, list[Link]] = await self._fetch_links(session, record_ids)
        return [self._to_record(row, links.get(row.id, [])) for row in rows]

    async def _fetch_links(
        self, session: Tx, record_ids: Sequence[str]
    ) -> dict[str, list[Link]]:
        """Returns map of record id -> its links in order."""
        links: dict[str, list[Link]] = {}
        for batch in get_batches(list(record_ids)):
            stmt: Select[str, str, str] = (
                select(
                    LinkModel.record_id,
                    LinkModel.property_name,
                    LinkModel.target_id,
                )
                .where(Conditions.match_any(LinkModel.record_id, batch))
                .order_by(LinkModel.record_id, LinkModel.position)
            )
            for record_id, prop_name, target_id in await session.execute(stmt):
                links.setdefault(record_id, []).append(Link(prop_name, target_id))
        return links

    @staticmethod
    def _to_record(row: RecordModel, links: list[Link]) -> Record:
        return Record(
            id=row.id,
            cls=row.cls,
            graph=row.graph,
            input=row.input,
            ontology_version=row.ontology_version,
            links=tuple(links),
            review=row.review,
            version=row.version,
        )
