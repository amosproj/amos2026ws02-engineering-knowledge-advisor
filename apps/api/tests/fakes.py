import json
from collections.abc import AsyncGenerator, Generator, Iterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, override

from services import Record, RecordLinkedError, RecordStore, Tx, UnstorableValueError
from services.catalog import CatalogService
from services.object_storage import ObjectStorage, StoredObject
from services.ograg.ontology import Ontology, to_list
from services.ograg.service import OgRagService
from services.records import ERROR_STILL_LINKED
from services.uploads import Upload, UploadStatus, UploadStore

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
        self.saves: int = 0
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
        self.saves += 1
        for rec in records:
            self.rows[rec.id] = replace(rec, version=str(self.saves))

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
    async def lock_record(self, record_id: str, tx: Tx) -> str | None:
        # nothing runs concurrently in memory
        found: Record | None = self.rows.get(record_id)
        return None if found is None else found.version

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


class MemoryUploadStore(UploadStore):
    """Uploads by file id. Nothing runs concurrently in memory, so nothing is locked."""

    def __init__(self) -> None:
        self.uploads: dict[str, Upload] = {}

    @override
    @asynccontextmanager
    async def limit_lock_wait(self, tx: Tx) -> AsyncGenerator[None]:
        yield

    @override
    async def start_upload(
        self, file_id: str, source_key: str, size_bytes: int, tx: Tx
    ) -> Upload | None:
        current: Upload | None = self.uploads.get(file_id)
        if current is not None and current.status in (
            UploadStatus.PROCESSING,
            UploadStatus.READY,
        ):
            return None
        now: datetime = datetime.now(UTC)
        self.uploads[file_id] = Upload(
            file_id, UploadStatus.UPLOADING, None, source_key, size_bytes, now, now
        )
        return self.uploads[file_id]

    @override
    async def delete_upload(self, file_id: str, tx: Tx) -> None:
        self.uploads.pop(file_id, None)

    @override
    async def get_uploads(self, file_ids: Sequence[str], tx: Tx) -> dict[str, Upload]:
        return {
            file_id: self.uploads[file_id]
            for file_id in file_ids
            if file_id in self.uploads
        }

    @override
    async def finish_upload(
        self, file_id: str, error_code: str | None, tx: Tx
    ) -> Upload | None:
        current: Upload | None = self.uploads.get(file_id)
        if current is None or current.status != UploadStatus.UPLOADING:
            return None
        status: UploadStatus = (
            UploadStatus.PROCESSING if error_code is None else UploadStatus.FAILED
        )
        self.uploads[file_id] = Upload(
            file_id,
            status,
            error_code,
            current.source_key,
            current.size_bytes,
            current.created_at,
            datetime.now(UTC),
        )
        return self.uploads[file_id]

    @override
    async def lock_next_to_process(self, tx: Tx) -> Upload | None:
        raise NotImplementedError

    @override
    async def set_ready(self, file_id: str, sha256: str, tx: Tx) -> None:
        raise NotImplementedError

    @override
    async def set_failed(self, file_id: str, error_code: str, tx: Tx) -> None:
        raise NotImplementedError

    @override
    async def move_to_back(self, file_id: str, tx: Tx) -> None:
        raise NotImplementedError

    @override
    async def get_abandoned_ids(self, max_age: timedelta, tx: Tx) -> list[str]:
        raise NotImplementedError

    @override
    async def lock_abandoned(
        self, file_id: str, max_age: timedelta, tx: Tx
    ) -> Upload | None:
        raise NotImplementedError

    @override
    async def get_kept_ids(self, file_ids: Sequence[str], tx: Tx) -> set[str]:
        raise NotImplementedError


class MemoryStorage(ObjectStorage):
    """Object sizes by key. Upload forms point to ``/storage/test`` and carry the key."""

    def __init__(self) -> None:
        self.sizes: dict[str, int] = {}
        self.deleted_keys: list[str] = []

    @override
    def ensure_bucket(self) -> None:
        raise NotImplementedError

    @override
    def create_upload_form(self, key: str, size: int) -> tuple[str, dict[str, str]]:
        return "/storage/test", {"key": key}

    @override
    def get_object_size(self, key: str) -> int | None:
        return self.sizes.get(key)

    @override
    def read_object(self, key: str, chunk_size: int) -> Generator[bytes] | None:
        raise NotImplementedError

    @override
    def list_objects(self, prefix: str) -> Iterator[list[StoredObject]]:
        raise NotImplementedError

    @override
    def delete_objects(self, keys: list[str]) -> None:
        raise NotImplementedError

    @override
    def delete_folders_quietly(self, prefixes: list[str]) -> None:
        for key in list(self.sizes):
            if key.startswith(tuple(prefixes)):
                self.deleted_keys.append(key)
                del self.sizes[key]


def make_catalog(ograg: OgRagService | None = None) -> CatalogService:
    """A catalog on ``ograg`` (or ``make_service()``) with the upload state and the files in memory."""
    return CatalogService(
        ograg if ograg is not None else make_service(),
        MemoryUploadStore(),
        MemoryStorage(),
    )
