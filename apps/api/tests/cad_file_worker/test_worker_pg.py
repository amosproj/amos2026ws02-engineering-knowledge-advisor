"""The CAD file worker on a scratch Postgres, with an in-memory object storage."""

import asyncio
import os
import threading
from collections.abc import AsyncGenerator, Callable, Coroutine, Generator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes import load_ontology
from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from cad_file_worker import cleanup
from cad_file_worker.cleanup import delete_orphan_objects, expire_abandoned_uploads
from cad_file_worker.processing import process_next_cad_upload
from db import TableName, Tables, define_tables
from services.catalog import CatalogService, PresignedForm
from services.object_storage import ObjectStorage, StoredObject
from services.ograg.ontology import Ontology
from services.ograg.service import OgRagService
from services.postgres.record_store import PgRecordStore
from services.postgres.upload_store import PgUploadStore
from services.uploads import Upload, UploadStatus

URL: str = os.environ.get("API_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not URL,
    reason="set API_TEST_DATABASE_URL to a scratch Postgres",
)

STEP: bytes = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
NOT_STEP: bytes = b"solid cube\nendsolid cube\n"
SELECT_OGRAG_TABLES: str = (
    "SELECT tablename FROM pg_tables"
    " WHERE schemaname = current_schema() AND tablename LIKE 'ograg\\_%'"
)
LONG_AGO: datetime = datetime(2020, 1, 1, tzinfo=UTC)

type Sessions = async_sessionmaker[AsyncSession]


class ContentStorage(ObjectStorage):
    """Objects by key with their content and when they were written."""

    def __init__(self) -> None:
        self.contents: dict[str, bytes] = {}
        self.modified: dict[str, datetime] = {}

    def put(self, key: str, content: bytes, modified: datetime | None = None) -> None:
        self.contents[key] = content
        self.modified[key] = modified or datetime.now(UTC)

    def ensure_bucket(self) -> None:
        raise NotImplementedError

    def create_upload_form(self, key: str, size: int) -> tuple[str, dict[str, str]]:
        return "/storage/test", {"key": key}

    def get_object_size(self, key: str) -> int | None:
        content: bytes | None = self.contents.get(key)
        return None if content is None else len(content)

    def read_object(self, key: str, chunk_size: int) -> Generator[bytes] | None:
        if key not in self.contents:
            return None
        content: bytes = self.contents[key]
        return (
            content[start : start + chunk_size]
            for start in range(0, len(content), chunk_size)
        )

    def list_objects(self, prefix: str) -> Iterator[list[StoredObject]]:
        yield [
            StoredObject(key, self.modified[key])
            for key in sorted(self.contents)
            if key.startswith(prefix)
        ]

    def delete_objects(self, keys: list[str]) -> None:
        for key in keys:
            self.contents.pop(key, None)

    def delete_folders_quietly(self, prefixes: list[str]) -> None:
        self.delete_objects(
            [key for key in self.contents if key.startswith(tuple(prefixes))]
        )


class Worker:
    """The catalog the worker runs with, and what the API does before."""

    def __init__(self, sessions: Sessions, catalog: CatalogService) -> None:
        self.sessions: Sessions = sessions
        self.catalog: CatalogService = catalog
        storage = catalog.storage
        assert isinstance(storage, ContentStorage)
        self.storage: ContentStorage = storage
        self.machine_id: str = ""

    async def add_file(self, content: bytes | None, name: str = "tray.step") -> str:
        """Creates a machine with a CAD file record and uploads ``content``. ``None`` uploads nothing."""
        async with self.sessions() as session, session.begin():
            self.machine_id = (
                await self.catalog.create_record(
                    session, {"@type": "Machine", "name": "Robot cell"}
                )
            ).record.id
            file_id: str = (
                await self.catalog.create_record(
                    session,
                    {"@type": "CadFile", "name": name, "partOf": self.machine_id},
                )
            ).record.id
            form: PresignedForm = await self.catalog.create_upload_form(
                session, file_id, len(content or b"x")
            )
        if content is not None:
            self.storage.put(form.fields["key"], content)
        return file_id

    async def add_processing_file(self, content: bytes | None) -> str:
        """A file the API queued for processing. ``None``: its object vanished meanwhile."""
        file_id: str = await self.add_file(content or STEP)
        async with self.sessions() as session, session.begin():
            await self.catalog.complete_upload(session, file_id)
        if content is None:
            self.storage.contents.clear()
        return file_id

    async def process(self) -> bool:
        return await process_next_cad_upload(
            self.sessions, self.catalog, threading.Event(), lambda: None
        )

    async def get_upload(self, file_id: str) -> Upload | None:
        async with self.sessions() as session:
            uploads: dict[str, Upload] = await self.catalog.uploads.get_uploads(
                [file_id], session
            )
        return uploads.get(file_id)

    async def get_status(self, record_id: str) -> UploadStatus | None:
        async with self.sessions() as session:
            return await self.catalog.get_status(session, record_id)


def run_async(check: Callable[[], Coroutine[Any, Any, None]]) -> None:
    asyncio.run(check(), loop_factory=asyncio.SelectorEventLoop)


@asynccontextmanager
async def open_worker() -> AsyncGenerator[Worker]:
    """Fresh tables with a machine."""
    engine: AsyncEngine = create_async_engine(URL)
    tables: Tables = define_tables(MetaData())
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP TABLE IF EXISTS "{TableName.CAD_UPLOADS}"'))
            for name in (await conn.execute(text(SELECT_OGRAG_TABLES))).scalars():
                await conn.execute(text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))
            await conn.run_sync(tables.metadata.create_all)
        ontology: Ontology = load_ontology()
        ograg = OgRagService(
            ontology,
            PgRecordStore(
                engine,
                tables,
                identity_property_names=ontology.get_identity_property_names(),
            ),
        )
        worker = Worker(
            async_sessionmaker(engine, expire_on_commit=False),
            CatalogService(ograg, PgUploadStore(tables), ContentStorage()),
        )
        yield worker
    finally:
        await engine.dispose()


def test_a_valid_step_file_becomes_ready():
    async def run_check() -> None:
        async with open_worker() as worker:
            assert not await worker.process()
            file_id: str = await worker.add_processing_file(STEP)

            assert await worker.process()
            upload: Upload | None = await worker.get_upload(file_id)
            assert upload is not None and upload.status == UploadStatus.READY
            assert await worker.get_status(worker.machine_id) == UploadStatus.READY
            assert worker.storage.contents
            assert not await worker.process()

    run_async(run_check)


@pytest.mark.parametrize(
    ("content", "error_code", "deleted"),
    [
        (NOT_STEP, "invalid_step_file", True),
        (None, "upload_not_found", False),
    ],
    ids=["not a step file", "object missing"],
)
def test_a_file_that_cannot_be_checked_fails(
    content: bytes | None, error_code: str, deleted: bool
):
    async def run_check() -> None:
        async with open_worker() as worker:
            file_id: str = await worker.add_processing_file(content)

            assert await worker.process()
            upload: Upload | None = await worker.get_upload(file_id)
            assert upload is not None
            assert (upload.status, upload.error_code) == ("failed", error_code)
            if deleted:
                assert worker.storage.contents == {}

    run_async(run_check)


def test_the_same_content_is_ready_on_two_machines():
    async def run_check() -> None:
        async with open_worker() as worker:
            first_id: str = await worker.add_processing_file(STEP)
            await worker.process()
            copy_id: str = await worker.add_processing_file(STEP)

            assert await worker.process()
            for file_id in (first_id, copy_id):
                upload: Upload | None = await worker.get_upload(file_id)
                assert upload is not None and upload.status == UploadStatus.READY
            assert len(worker.storage.contents) == 2

    run_async(run_check)


def test_abandoned_uploads_are_dropped_and_their_records_kept(
    monkeypatch: pytest.MonkeyPatch,
):
    async def run_check() -> None:
        async with open_worker() as worker:
            abandoned_id: str = await worker.add_file(STEP)
            queued_id: str = await worker.add_processing_file(STEP + b"\n")
            monkeypatch.setattr(cleanup, "ABANDONED_UPLOAD_AGE", timedelta(0))

            await expire_abandoned_uploads(
                worker.sessions, worker.catalog, threading.Event(), lambda: None
            )

            assert await worker.get_upload(abandoned_id) is None
            async with worker.sessions() as session:
                kept = await worker.catalog.get_record(session, abandoned_id)
            assert kept.id == abandoned_id
            assert await worker.get_status(abandoned_id) is None
            queued: Upload | None = await worker.get_upload(queued_id)
            assert queued is not None and queued.status == UploadStatus.PROCESSING
            assert len(worker.storage.contents) == 1
            # the kept record can get a new upload
            async with worker.sessions() as session, session.begin():
                await worker.catalog.create_upload_form(session, abandoned_id, 1)

    run_async(run_check)


def test_old_objects_without_a_kept_upload_are_deleted(
    monkeypatch: pytest.MonkeyPatch,
):
    async def run_check() -> None:
        async with open_worker() as worker:
            kept_id: str = await worker.add_file(STEP)
            failed_id: str = await worker.add_processing_file(NOT_STEP)
            await worker.process()
            storage: ContentStorage = worker.storage
            kept_key: str = f"files/{kept_id}/source.step"
            storage.put(kept_key, STEP, LONG_AGO)
            storage.put(f"files/{failed_id}/source.step", NOT_STEP, LONG_AGO)
            storage.put("files/deleted-id/source.step", STEP, LONG_AGO)
            storage.put("files/young-id/source.step", STEP)
            storage.put("files/stray.step", STEP, LONG_AGO)
            monkeypatch.setattr(cleanup, "ORPHAN_OBJECT_AGE", timedelta(hours=1))

            await delete_orphan_objects(
                worker.sessions, worker.catalog, threading.Event(), lambda: None
            )

            assert sorted(storage.contents) == sorted(
                [kept_key, "files/stray.step", "files/young-id/source.step"]
            )

    run_async(run_check)
