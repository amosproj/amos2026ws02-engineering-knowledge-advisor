import json
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, override

from services import Record, RecordLinkedError, RecordStore, Tx, UnstorableValueError
from services.ograg.ontology import Ontology, to_list
from services.ograg.service import OgRagService
from services.records import ERROR_STILL_LINKED

ONTOLOGY_PATH: Path = Path(__file__).parents[1] / "ontology_v0.jsonld"
ERROR_ESCAPE_SEQUENCE: str = (
    "cannot store the value: unsupported Unicode escape sequence"
)
ERROR_BROKEN_CHARACTER: str = "cannot store the value: text with a broken character"


def _check_storable(value: object) -> None:
    """Refuse what Postgres refuses (NUL characters, lone surrogates), like ``PgRecordStore`` does."""
    if isinstance(value, str):
        if "\x00" in value:
            raise UnstorableValueError(ERROR_ESCAPE_SEQUENCE)
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise UnstorableValueError(ERROR_BROKEN_CHARACTER) from exc
    elif isinstance(value, dict):
        for k, v in value.items():
            _check_storable(k)
            _check_storable(v)
    elif isinstance(value, (list, tuple)):
        for val in value:
            _check_storable(val)


class MemoryRecordStore(RecordStore):
    """Committed at once unless the service owns the transaction: then a failing write rolls back.

    ``tx`` from the caller is ignored (there is nothing to join). ``identity_property_names``: record class ->
    names of its identity properties (``Ontology.get_identity_property_names()``), used by ``find_record_ids``.
    """

    def __init__(self, identity_property_names: dict[str, list[str]] | None = None):
        self.rows: dict[str, Record] = {}
        self.identity_property_names: dict[str, list[str]] = (
            identity_property_names or {}
        )

    @override
    async def save_records(
        self, records: Sequence[Record], tx: Tx | None = None
    ) -> None:
        for rec in records:
            _check_storable(
                [
                    rec.id,
                    rec.graph,
                    rec.input,
                    [(link.property_name, link.target_id) for link in rec.links],
                ]
            )
        for rec in records:
            self.rows[rec.id] = rec

    @override
    async def get_record(self, record_id: str, tx: Tx | None = None) -> Record | None:
        _check_storable(record_id)
        return self.rows.get(record_id)

    @override
    async def delete_record(self, record_id: str, tx: Tx | None = None) -> bool:
        linking: list[Record] = await self.get_linking_records([record_id])
        linking_ids: list[str] = sorted(
            {rec.id for rec in linking if rec.id != record_id}
        )
        if linking_ids:
            raise RecordLinkedError(
                ERROR_STILL_LINKED.format(record_id=record_id, linking_ids=linking_ids)
            )
        return self.rows.pop(record_id, None) is not None

    @override
    async def get_all_records(self, tx: Tx | None = None) -> list[Record]:
        return [self.rows[rec_id] for rec_id in sorted(self.rows)]

    @override
    async def get_records(
        self, record_ids: Sequence[str], tx: Tx | None = None
    ) -> list[Record]:
        return [self.rows[rec_id] for rec_id in record_ids if rec_id in self.rows]

    @override
    @asynccontextmanager
    async def open_transaction(self, tx: Tx | None = None) -> AsyncGenerator[Tx]:
        if tx is not None:
            yield tx
            return
        before = dict(self.rows)
        try:
            yield None
        except BaseException:
            self.rows = before  # roll back
            raise

    @override
    async def get_ontology_versions(self, tx: Tx | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for rec in self.rows.values():
            counts[rec.ontology_version] = counts.get(rec.ontology_version, 0) + 1
        return counts

    @override
    async def get_linking_records(
        self, target_ids: Sequence[str], tx: Tx | None = None
    ) -> list[Record]:
        wanted_ids: set[str] = set(target_ids)
        return [
            rec
            for rec in await self.get_all_records()
            if any(link.target_id in wanted_ids for link in rec.links)
        ]

    @override
    async def get_records_to_review(self, tx: Tx | None = None) -> list[Record]:
        return [rec for rec in await self.get_all_records() if rec.review]

    @override
    async def get_records_by_class(
        self, cls: str, tx: Tx | None = None
    ) -> list[Record]:
        return [rec for rec in await self.get_all_records() if rec.cls == cls]

    @override
    async def lock_record(self, record_id: str, tx: Tx) -> None:
        pass  # nothing runs concurrently in memory

    @override
    async def find_record_ids(
        self, cls: str, text: str, tx: Tx | None = None
    ) -> list[str]:
        wanted: str = text.casefold()
        prop_names: list[str] = self.identity_property_names.get(cls, [])
        return [
            rec.id
            for rec in await self.get_all_records()
            if rec.cls == cls
            and (
                rec.id.casefold() == wanted
                or any(
                    str(val).casefold() == wanted
                    for prop_name in prop_names
                    for val in to_list(rec.graph.get(prop_name, []))
                )
            )
        ]


def load_ontology() -> Ontology:
    return Ontology.load(ONTOLOGY_PATH)


def load_document() -> dict[str, Any]:
    """The parsed ontology file, a fresh copy each time: tests may change it."""
    return json.loads(ONTOLOGY_PATH.read_text("utf-8"))


def build_ontology_with(*items: dict[str, Any]) -> Ontology:
    """The ontology with ``items`` added to its ``@graph``."""
    document: dict[str, Any] = load_document()
    document["@graph"] += list(items)
    return Ontology.from_jsonld(document)


def make_service(
    ontology: Ontology | None = None, store: RecordStore | None = None
) -> OgRagService:
    """A record service on the in-memory store (or on ``store``), without an index."""
    ontology = ontology or load_ontology()
    return OgRagService(
        ontology,
        store
        if store is not None
        else MemoryRecordStore(ontology.get_identity_property_names()),
    )
