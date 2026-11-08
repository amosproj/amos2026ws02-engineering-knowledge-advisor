"""The upload store on a scratch Postgres: what the API and the CAD file worker rely on."""

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import MetaData, insert, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from db import CommonColumn, RecordColumn, TableName, Tables, define_tables
from services.postgres.upload_store import PgUploadStore
from services.uploads import Upload, UploadStatus

URL: str = os.environ.get("API_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not URL,
    reason="set API_TEST_DATABASE_URL to a scratch Postgres",
)

FIRST_ID: str = "file-1"
SECOND_ID: str = "file-2"
MISSING_ID: str = "file-9"
SIZE: int = 300
SHA256: str = "a" * 64
FILE_MISMATCH: str = "file_mismatch"
SELECT_OGRAG_TABLES: str = (
    "SELECT tablename FROM pg_tables"
    " WHERE schemaname = current_schema() AND tablename LIKE 'ograg\\_%'"
)

type Sessions = async_sessionmaker[AsyncSession]


def run_async(check: Callable[[], Coroutine[Any, Any, None]]) -> None:
    asyncio.run(check(), loop_factory=asyncio.SelectorEventLoop)


@asynccontextmanager
async def open_store(*file_ids: str) -> AsyncIterator[tuple[PgUploadStore, Sessions]]:
    """Fresh tables with one record per file id, each upload registered (``uploading``), in this order."""
    engine: AsyncEngine = create_async_engine(URL)
    tables: Tables = define_tables(MetaData())
    store = PgUploadStore(tables)
    sessions: Sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP TABLE IF EXISTS "{TableName.CAD_UPLOADS}"'))
            for name in (await conn.execute(text(SELECT_OGRAG_TABLES))).scalars():
                await conn.execute(text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))
            await conn.run_sync(tables.metadata.create_all)
        for file_id in file_ids:
            async with sessions() as session, session.begin():
                await session.execute(
                    insert(tables.records).values(
                        {
                            CommonColumn.ID: file_id,
                            RecordColumn.CLS: "CadFile",
                            RecordColumn.GRAPH: {},
                            RecordColumn.INPUT: {},
                            RecordColumn.ONTOLOGY_VERSION: "test",
                        }
                    )
                )
                await store.start_upload(
                    file_id, f"files/{file_id}/source.step", SIZE, session
                )
        yield store, sessions
    finally:
        await engine.dispose()


async def get_upload(store: PgUploadStore, sessions: Sessions, file_id: str) -> Upload:
    async with sessions() as session:
        return (await store.get_uploads([file_id], session))[file_id]


async def finish(store: PgUploadStore, sessions: Sessions, *file_ids: str) -> None:
    """Moves the files to processing, one transaction each, so they queue in this order."""
    for file_id in file_ids:
        async with sessions() as session, session.begin():
            await store.finish_upload(file_id, None, session)


def test_an_upload_is_finished_once():
    async def run_check() -> None:
        async with open_store(FIRST_ID, SECOND_ID) as (store, sessions):
            async with sessions() as session, session.begin():
                finished: Upload | None = await store.finish_upload(
                    FIRST_ID, None, session
                )
                failed: Upload | None = await store.finish_upload(
                    SECOND_ID, FILE_MISMATCH, session
                )
                again: Upload | None = await store.finish_upload(
                    FIRST_ID, None, session
                )
            assert finished is not None and finished.status == UploadStatus.PROCESSING
            assert failed is not None and failed.status == UploadStatus.FAILED
            assert failed.error_code == FILE_MISMATCH
            assert again is None

    run_async(run_check)


def test_the_worker_takes_the_oldest_waiting_file_and_skips_locked_ones():
    async def run_check() -> None:
        async with open_store(FIRST_ID, SECOND_ID) as (store, sessions):
            await finish(store, sessions, FIRST_ID, SECOND_ID)
            async with sessions() as first, first.begin():
                taken: Upload | None = await store.lock_next_to_process(first)
                async with sessions() as second, second.begin():
                    next_taken: Upload | None = await store.lock_next_to_process(second)
                    # a locked file is not moved
                    await store.move_to_back(FIRST_ID, second)
            assert taken is not None and taken.file_id == FIRST_ID
            assert next_taken is not None and next_taken.file_id == SECOND_ID

            async with sessions() as session, session.begin():
                await store.move_to_back(FIRST_ID, session)
            async with sessions() as session, session.begin():
                after_move: Upload | None = await store.lock_next_to_process(session)
            assert after_move is not None and after_move.file_id == SECOND_ID

    run_async(run_check)


def test_the_same_content_may_be_ready_twice():
    async def run_check() -> None:
        async with open_store(FIRST_ID, SECOND_ID) as (store, sessions):
            await finish(store, sessions, FIRST_ID, SECOND_ID)
            async with sessions() as session, session.begin():
                await store.set_ready(FIRST_ID, SHA256, session)
                await store.set_ready(SECOND_ID, SHA256, session)

            for file_id in (FIRST_ID, SECOND_ID):
                assert (await get_upload(store, sessions, file_id)).status == "ready"

    run_async(run_check)


def test_abandoned_uploads_are_found_by_age():
    async def run_check() -> None:
        async with open_store(FIRST_ID, SECOND_ID) as (store, sessions):
            await finish(store, sessions, SECOND_ID)
            async with sessions() as session, session.begin():
                old_ids: list[str] = await store.get_abandoned_ids(
                    timedelta(0), session
                )
                young_ids: list[str] = await store.get_abandoned_ids(
                    timedelta(hours=1), session
                )
                locked: Upload | None = await store.lock_abandoned(
                    FIRST_ID, timedelta(0), session
                )
                not_abandoned: Upload | None = await store.lock_abandoned(
                    SECOND_ID, timedelta(0), session
                )
            assert old_ids == [FIRST_ID]
            assert young_ids == []
            assert locked is not None and locked.source_key.endswith("source.step")
            assert not_abandoned is None

    run_async(run_check)


def test_failed_and_missing_files_are_not_kept():
    async def run_check() -> None:
        async with open_store(FIRST_ID, SECOND_ID) as (store, sessions):
            async with sessions() as session, session.begin():
                await store.finish_upload(SECOND_ID, FILE_MISMATCH, session)
                kept_ids: set[str] = await store.get_kept_ids(
                    [FIRST_ID, SECOND_ID, MISSING_ID], session
                )
            assert kept_ids == {FIRST_ID}

    run_async(run_check)


def test_an_upload_restarts_until_its_file_is_processed():
    async def run_check() -> None:
        async with open_store(FIRST_ID, SECOND_ID) as (store, sessions):
            await finish(store, sessions, SECOND_ID)
            async with sessions() as session, session.begin():
                await store.finish_upload(FIRST_ID, FILE_MISMATCH, session)
                restarted: Upload | None = await store.start_upload(
                    FIRST_ID, f"files/{FIRST_ID}/source.step", SIZE + 1, session
                )
                kept: Upload | None = await store.start_upload(
                    SECOND_ID, f"files/{SECOND_ID}/source.step", SIZE + 1, session
                )
            assert restarted is not None
            assert (restarted.status, restarted.error_code, restarted.size_bytes) == (
                "uploading",
                None,
                SIZE + 1,
            )
            assert kept is None
            assert (await get_upload(store, sessions, SECOND_ID)).size_bytes == SIZE

            async with sessions() as session, session.begin():
                await store.delete_upload(FIRST_ID, session)
                remaining: dict[str, Upload] = await store.get_uploads(
                    [FIRST_ID, SECOND_ID], session
                )
            assert list(remaining) == [SECOND_ID]

    run_async(run_check)
