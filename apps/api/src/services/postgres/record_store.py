from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any, override

from sqlalchemy import (
    Column,
    ColumnElement,
    RowMapping,
    Select,
    Table,
    delete,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.dml import ReturningDelete

from services import Json, Link, Record, RecordLinkedError, RecordStore
from services.postgres.names import CommonColumn, LinkColumn, RecordColumn
from services.postgres.shared import Conditions, Statements
from services.postgres.tables import Tables
from services.postgres.transaction import PgTx, get_batches, get_transaction
from services.records import ERROR_STILL_LINKED


class PgRecordStore(RecordStore):
    """Postgres-based ``RecordStore``.

    Links are rows of ``ograg_links`` with foreign keys: ``ON DELETE CASCADE`` on source, ``RESTRICT`` on target.
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
        engine: AsyncEngine,
        tables: Tables,
        identity_property_names: Mapping[str, Sequence[str]] | None = None,
    ):
        """
        Args:
            engine: asyncio engine.
            tables: from ``define_tables()``.
            identity_property_names: record class -> names of its identity properties.
        """
        self.engine: AsyncEngine = engine
        self.table: Table = tables.records
        self.links: Table = tables.links
        self.identity_property_names: dict[str, list[str]] = {
            cls: list(prop_names)
            for cls, prop_names in (identity_property_names or {}).items()
        }

    @override
    async def save_records(
        self, records: Sequence[Record], tx: PgTx | None = None
    ) -> None:
        if not records:
            return
        async with get_transaction(self.engine, tx) as conn:
            await conn.execute(
                self._build_upsert(), [self._to_row(rec) for rec in records]
            )
            await self._replace_links(conn, records)

    @override
    async def get_record(self, record_id: str, tx: PgTx | None = None) -> Record | None:
        async with get_transaction(self.engine, tx) as conn:
            found: list[Record] = await self._fetch_records(
                conn, self.table.c[CommonColumn.ID] == record_id
            )
        return found[0] if found else None

    @override
    async def delete_record(self, record_id: str, tx: PgTx | None = None) -> bool:
        async with get_transaction(self.engine, tx) as conn:
            linking_ids: list[str] = await self._get_linking_ids(conn, record_id)
            if linking_ids:
                raise RecordLinkedError(
                    ERROR_STILL_LINKED.format(
                        record_id=record_id, linking_ids=linking_ids
                    )
                )

            # delete outgoing links, including self links
            own_links_condition: ColumnElement[bool] = (
                self.links.c[CommonColumn.RECORD_ID] == record_id
            )
            await conn.execute(delete(self.links).where(own_links_condition))

            # delete record row
            deleted: ReturningDelete[Any] = (
                delete(self.table)
                .where(self.table.c[CommonColumn.ID] == record_id)
                .returning(self.table.c[CommonColumn.ID])
            )
            return (await conn.execute(deleted)).first() is not None

    @override
    async def get_all_records(self, tx: PgTx | None = None) -> list[Record]:
        async with get_transaction(self.engine, tx) as conn:
            return await self._fetch_records(conn)

    @override
    async def get_records(
        self, record_ids: Sequence[str], tx: PgTx | None = None
    ) -> list[Record]:
        found: list[Record] = []
        async with get_transaction(self.engine, tx) as conn:
            for batch in get_batches(list(record_ids)):
                found += await self._fetch_records(
                    conn, Conditions.match_any(self.table.c[CommonColumn.ID], batch)
                )
        return found

    @override
    @asynccontextmanager
    async def open_transaction(self, tx: PgTx | None = None) -> AsyncGenerator[PgTx]:
        async with get_transaction(self.engine, tx) as conn:
            yield conn

    @override
    async def get_ontology_versions(self, tx: PgTx | None = None) -> dict[str, int]:
        version: Column[Any] = self.table.c[RecordColumn.ONTOLOGY_VERSION]
        stmt: Select[Any, int] = select(version, func.count()).group_by(version)
        async with get_transaction(self.engine, tx) as conn:
            return {v: count for v, count in (await conn.execute(stmt)).all()}

    @override
    async def get_linking_records(
        self, target_ids: Sequence[str], tx: PgTx | None = None
    ) -> list[Record]:
        found: dict[str, Record] = {}
        async with get_transaction(self.engine, tx) as conn:
            for batch in get_batches(list(target_ids)):
                linking_id_query: Select[Any] = select(
                    self.links.c[CommonColumn.RECORD_ID]
                ).where(Conditions.match_any(self.links.c[LinkColumn.TARGET_ID], batch))
                records: list[Record] = await self._fetch_records(
                    conn, self.table.c[CommonColumn.ID].in_(linking_id_query)
                )
                found.update((rec.id, rec) for rec in records)
        return [found[rec_id] for rec_id in sorted(found)]

    @override
    async def get_records_to_review(self, tx: PgTx | None = None) -> list[Record]:
        async with get_transaction(self.engine, tx) as conn:
            return await self._fetch_records(
                conn, self.table.c[RecordColumn.REVIEW] != ""
            )

    @override
    async def find_record_ids(
        self, cls: str, text: str, tx: PgTx | None = None
    ) -> list[str]:
        stmt: Select[Any] = (
            select(self.table.c[CommonColumn.ID])
            .where(
                self.table.c[RecordColumn.CLS] == cls,
                self.table.c[RecordColumn.IDENTITY_VALUES].contains([text.casefold()]),
            )
            .order_by(self.table.c[CommonColumn.ID])
        )
        async with get_transaction(self.engine, tx) as conn:
            return list((await conn.execute(stmt)).scalars())

    def _build_upsert(self) -> Insert:
        """Returns an update-or-insert action."""
        stmt: Insert = insert(self.table)
        replaced: dict[str, ColumnElement[Any]] = {
            col: stmt.excluded[col]
            for col in (*self.COLUMNS, RecordColumn.IDENTITY_VALUES)
            if col != CommonColumn.ID
        }
        return stmt.on_conflict_do_update(
            index_elements=[self.table.c[CommonColumn.ID]],
            set_={**replaced, RecordColumn.UPDATED_AT: func.now()},
        )

    def _to_row(self, record: Record) -> dict[str, Any]:
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
            value: Json = record.graph.get(prop_name)
            items: list[Json] = value if isinstance(value, list) else [value]
            values += [str(item).casefold() for item in items if item is not None]
        return list(dict.fromkeys(values))

    async def _replace_links(self, conn: PgTx, records: Sequence[Record]) -> None:
        """Updates links of ``records``, in link order. ``records`` may be thousands."""
        # delete old links
        await Statements.delete_matching(
            conn, self.links.c[CommonColumn.RECORD_ID], [rec.id for rec in records]
        )

        # insert new links
        rows: list[dict[str, Any]] = self._to_link_rows(records)
        if rows:
            await conn.execute(Statements.build_unnest_insert(self.links, rows))

    @staticmethod
    def _to_link_rows(records: Sequence[Record]) -> list[dict[str, Any]]:
        """Returns one row per record link. ``position`` keeps their order."""
        return [
            {
                CommonColumn.RECORD_ID: rec.id,
                LinkColumn.POSITION: position,
                LinkColumn.PROPERTY_NAME: link.property_name,
                LinkColumn.TARGET_ID: link.target_id,
            }
            for rec in records
            for position, link in enumerate(rec.links)
        ]

    async def _get_linking_ids(self, conn: PgTx, record_id: str) -> list[str]:
        """Returns sorted ids of records that link to ``record_id``, excluding ``record_id``."""
        stmt: Select[Any] = select(self.links.c[CommonColumn.RECORD_ID]).where(
            self.links.c[LinkColumn.TARGET_ID] == record_id,
            self.links.c[CommonColumn.RECORD_ID] != record_id,
        )
        return sorted(set((await conn.execute(stmt)).scalars()))

    def _select_records(self) -> Select:
        """Returns select statement for all record columns, sorted by id."""
        return select(*(self.table.c[col] for col in self.COLUMNS)).order_by(
            self.table.c[CommonColumn.ID]
        )

    async def _fetch_records(
        self, conn: PgTx, *conditions: ColumnElement[bool]
    ) -> list[Record]:
        """Returns records matching all ``conditions`` sorted by id. Returns all records if ``conditions`` is empty."""
        stmt: Select = self._select_records().where(*conditions)
        rows: Sequence[RowMapping] = (await conn.execute(stmt)).mappings().all()
        record_ids: list[str] = [row[CommonColumn.ID] for row in rows]
        links: dict[str, list[Link]] = await self._fetch_links(conn, record_ids)
        return [
            self._to_record(row, links.get(rec_id, []))
            for row, rec_id in zip(rows, record_ids)
        ]

    async def _fetch_links(
        self, conn: PgTx, record_ids: Sequence[str]
    ) -> dict[str, list[Link]]:
        """Returns map of record id -> its links in order."""
        links: dict[str, list[Link]] = {}
        for batch in get_batches(list(record_ids)):
            stmt: Select[Any, Any, Any] = (
                select(
                    self.links.c[CommonColumn.RECORD_ID],
                    self.links.c[LinkColumn.PROPERTY_NAME],
                    self.links.c[LinkColumn.TARGET_ID],
                )
                .where(
                    Conditions.match_any(self.links.c[CommonColumn.RECORD_ID], batch)
                )
                .order_by(
                    self.links.c[CommonColumn.RECORD_ID],
                    self.links.c[LinkColumn.POSITION],
                )
            )
            for record_id, prop_name, target_id in await conn.execute(stmt):
                links.setdefault(record_id, []).append(Link(prop_name, target_id))
        return links

    @staticmethod
    def _to_record(row: RowMapping, links: list[Link]) -> Record:
        return Record(
            row[CommonColumn.ID],
            row[RecordColumn.CLS],
            row[RecordColumn.GRAPH],
            row[RecordColumn.INPUT],
            row[RecordColumn.ONTOLOGY_VERSION],
            tuple(links),
            row[RecordColumn.REVIEW],
        )
