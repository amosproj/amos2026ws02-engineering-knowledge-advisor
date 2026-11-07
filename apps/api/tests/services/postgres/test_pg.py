import asyncio
import os
from collections.abc import AsyncGenerator, Callable, Coroutine, Sequence
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Any

import pytest
from fakes import MemoryStorage, load_ontology
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import assert_mentions
from httpx2 import Response
from record_store_checks import CHECK_IDS, CHECKS, IDENTITY_PROPERTY_NAMES, Check
from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from api.router_records import v1_records_router
from db import TableName, Tables, define_tables
from db.session import create_sessionmaker
from handler.exception_handler import register
from handler.service_exception_handler import register as register_service
from services import Lane, SearchMode, UnstorableValueError
from services.catalog import CatalogService
from services.ograg.ontology import Ontology
from services.ograg.service import DeleteResult, OgRagService, RecordError
from services.postgres.record_store import PgRecordStore
from services.postgres.upload_store import PgUploadStore

URL: str = os.environ.get("API_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not URL,
    reason="set API_TEST_DATABASE_URL to a scratch Postgres",
)

PROBLEM_JSON: str = "application/problem+json"
RECORDS_URL: str = "/api/v1/records"
MACHINE_ID: str = "RC-01"
OTHER_MACHINE_ID: str = "RC-02"
GROUP_ID: str = "AG-1"
ORPHAN_ID: str = "AG-2"  # links to a machine that does not exist
MISSING_MACHINE_ID: str = "RC-09"  # machine the orphan links to
UNSTORABLE_NAME: str = "nul \x00 byte"
MACHINE: dict[str, Any] = {
    "@type": "Machine",
    "identifier": MACHINE_ID,
    "name": "Robot cell",
}
GROUP: dict[str, Any] = {
    "@type": "AssemblyGroup",
    "name": "Input tray",
    "rootOf": MACHINE_ID,
}
ORPHAN: dict[str, Any] = {**GROUP, "rootOf": MISSING_MACHINE_ID}
ITEM_ID: str = "KI-1"
ITEM: dict[str, Any] = {
    "@type": "KnowledgeItem",
    "properties": {
        "@type": "KnowledgeProperties",
        "name": "Chamfer",
        "statement": "Chamfer the nest.",
    },
    "appliesTo": [GROUP_ID],
}
# Async psycopg refuses Windows' default ProactorEventLoop.
SELECTOR_LOOP: dict[str, Any] = {"loop_factory": asyncio.SelectorEventLoop}
SELECT_OGRAG_TABLES: str = (
    "SELECT tablename FROM pg_tables"
    " WHERE schemaname = current_schema() AND tablename LIKE 'ograg\\_%'"
)


def run_async(check: Callable[[], Coroutine[Any, Any, None]]) -> None:
    asyncio.run(check(), loop_factory=asyncio.SelectorEventLoop)


async def drop_ograg_tables(conn: AsyncConnection) -> None:
    """Drops every ``ograg_*`` table, also ones the code no longer defines (left from an older schema)."""
    names: Sequence[str] = (
        (await conn.execute(text(SELECT_OGRAG_TABLES))).scalars().all()
    )
    for name in names:
        await conn.execute(text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))


async def create_fresh_tables(engine: AsyncEngine) -> Tables:
    tables: Tables = define_tables(MetaData())
    async with engine.begin() as conn:
        # cad_uploads first: dropping ograg_records with CASCADE would only drop its foreign key
        await conn.execute(text(f'DROP TABLE IF EXISTS "{TableName.CAD_UPLOADS}"'))
        await drop_ograg_tables(conn)
        await conn.run_sync(tables.metadata.create_all)
    return tables


def create_service_on(engine: AsyncEngine, tables: Tables) -> OgRagService:
    ontology: Ontology = load_ontology()
    store = PgRecordStore(
        engine, tables, identity_property_names=ontology.get_identity_property_names()
    )
    return OgRagService(ontology, store)


@pytest.mark.parametrize(
    "member",
    [*Lane, *SearchMode],
    ids=lambda member: f"{type(member).__name__}.{member.name}",
)
def test_enum_members_are_written_as_their_value(member: StrEnum):
    async def run_check() -> None:
        engine: AsyncEngine = create_async_engine(URL)
        try:
            async with engine.connect() as conn:
                written = await conn.scalar(
                    text("SELECT CAST(:v AS text)"), {"v": member}
                )
            assert written == member.value
        finally:
            await engine.dispose()

    run_async(run_check)


def test_identity_values_of_records_have_a_gin_index():
    async def run_check() -> None:
        engine: AsyncEngine = create_async_engine(URL)
        try:
            await create_fresh_tables(engine)
            async with engine.connect() as conn:
                definition: str | None = await conn.scalar(
                    text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
                    {"name": f"{TableName.RECORDS}_identity_values"},
                )
            assert definition is not None
            assert "gin" in definition.lower()
        finally:
            await engine.dispose()

    run_async(run_check)


@pytest.mark.parametrize("check", CHECKS, ids=CHECK_IDS)
def test_record_store_contract_on_postgres(check: Check):
    async def run_check() -> None:
        engine: AsyncEngine = create_async_engine(URL)
        try:
            tables: Tables = await create_fresh_tables(engine)
            await check(
                PgRecordStore(
                    engine, tables, identity_property_names=IDENTITY_PROPERTY_NAMES
                )
            )
        finally:
            await engine.dispose()

    run_async(run_check)


def test_writes_join_the_callers_transaction_and_roll_back_with_it():
    async def run_check() -> None:
        engine: AsyncEngine = create_async_engine(URL)
        service: OgRagService = create_service_on(
            engine, await create_fresh_tables(engine)
        )
        try:
            # In an AsyncConnection: visible inside, gone after the rollback.
            async with engine.connect() as conn, conn.begin() as transaction:
                await service.upsert_record(MACHINE_ID, MACHINE, tx=conn)
                assert await service.store.get_record(MACHINE_ID, tx=conn) is not None
                assert (
                    await service.store.get_record(MACHINE_ID) is None
                )  # not committed
                await transaction.rollback()
            assert await service.store.get_record(MACHINE_ID) is None

            # In an AsyncSession: the second write sees the first one's machine.
            async with AsyncSession(engine) as session, session.begin():
                await service.upsert_record(MACHINE_ID, MACHINE, tx=session)
                await service.upsert_record(GROUP_ID, GROUP, tx=session)
            stored: list[dict[str, Any]] = await service.get_records()
            assert [rec["@id"] for rec in stored] == [GROUP_ID, MACHINE_ID]

            machine: dict[str, Any] = {**MACHINE, "identifier": OTHER_MACHINE_ID}
            with pytest.raises(RecordError, match=MISSING_MACHINE_ID):
                async with AsyncSession(engine) as session, session.begin():
                    await service.upsert_record(OTHER_MACHINE_ID, machine, tx=session)
                    await service.upsert_record(ORPHAN_ID, ORPHAN, tx=session)
            # Rolled back with the failing write:
            assert await service.store.get_record(OTHER_MACHINE_ID) is None

            unstorable: dict[str, Any] = {**MACHINE, "name": UNSTORABLE_NAME}
            with pytest.raises(UnstorableValueError):
                async with AsyncSession(engine) as session, session.begin():
                    await service.upsert_record(
                        OTHER_MACHINE_ID, unstorable, tx=session
                    )
            stored: list[dict[str, Any]] = await service.get_records()
            assert [rec["@id"] for rec in stored] == [GROUP_ID, MACHINE_ID]

            # In the service's own transaction:
            result: DeleteResult = await service.delete_record(MACHINE_ID)
            assert (result.deleted_ids, result.marked_ids) == ([MACHINE_ID], [GROUP_ID])
        finally:
            await engine.dispose()

    run_async(run_check)


def test_the_records_api_commits_or_rolls_back_with_the_request():
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        engine: AsyncEngine = create_async_engine(URL)
        app.state.sessions = create_sessionmaker(engine)
        tables: Tables = await create_fresh_tables(engine)
        service: OgRagService = create_service_on(engine, tables)
        # the parents of the linked item
        await service.upsert_record(MACHINE_ID, MACHINE)
        await service.upsert_record(GROUP_ID, GROUP)
        app.state.ograg = service
        app.state.catalog = CatalogService(
            service, PgUploadStore(tables), MemoryStorage()
        )
        yield
        await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    register(app)
    register_service(app)
    app.include_router(v1_records_router)

    with TestClient(
        app, raise_server_exceptions=False, backend_options=SELECTOR_LOOP
    ) as client:
        assert client.put(f"{RECORDS_URL}/{ITEM_ID}", json=ITEM).status_code == 200

        unstorable: dict[str, Any] = {
            **ITEM,
            "properties": {"statement": UNSTORABLE_NAME},
        }
        bad: Response = client.put(f"{RECORDS_URL}/KI-2", json=unstorable)
        assert bad.status_code == 422
        assert bad.headers["content-type"] == PROBLEM_JSON

        orphan: dict[str, Any] = {**ITEM, "appliesTo": [ORPHAN_ID]}
        missing: Response = client.put(f"{RECORDS_URL}/KI-3", json=orphan)
        assert missing.status_code == 422
        assert_mentions(missing.json()["detail"], "appliesTo", ORPHAN_ID)

        stored: list[dict[str, Any]] = client.get(RECORDS_URL).json()
        # the failed ones left nothing
        assert [rec["@id"] for rec in stored] == [GROUP_ID, ITEM_ID, MACHINE_ID]

        deleted: dict[str, Any] = client.delete(f"{RECORDS_URL}/{ITEM_ID}").json()
        assert deleted == {"deletedIds": [ITEM_ID], "markedIds": []}
        assert client.delete(f"{RECORDS_URL}/{ITEM_ID}").status_code == 404
