"""Catalog routes on a scratch Postgres, with an in-memory object storage."""

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Generator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import psycopg
import pytest
from fakes import load_ontology
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from api.router_catalog import v1_catalog_router
from db import ModelBase, create_sessionmaker, get_ograg_tables
from handler.exception_handler import register
from handler.service_exception_handler import register as register_service
from services.catalog import CatalogService
from services.object_storage import ObjectStorage, StoredObject
from services.ograg.ontology import Ontology
from services.ograg.service import OgRagService
from services.postgres.record_store import PgRecordStore

URL: str = os.environ.get("API_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not URL,
    reason="set API_TEST_DATABASE_URL to a scratch Postgres",
)

API: str = "/api/v1"
PROBLEM_JSON: str = "application/problem+json"
SIZE: int = 300
# async psycopg refuses default Windows ProactorEventLoop
SELECTOR_LOOP: dict[str, Any] = {"loop_factory": asyncio.SelectorEventLoop}


class FakeStorage(ObjectStorage):
    """Objects by key with their size. Checks that deletions run after the commit."""

    def __init__(self, sync_engine: Engine) -> None:
        self.sizes: dict[str, int] = {}
        self.deleted_keys: list[str] = []
        self.sync_engine: Engine = sync_engine

    def ensure_bucket(self) -> None:
        raise NotImplementedError

    def create_upload_form(self, key: str, size: int) -> tuple[str, dict[str, str]]:
        return "/storage/test", {"key": key}

    def get_object_size(self, key: str) -> int | None:
        return self.sizes.get(key)

    def read_object(self, key: str, chunk_size: int) -> Generator[bytes] | None:
        raise NotImplementedError

    def list_objects(self, prefix: str) -> Iterator[list[StoredObject]]:
        raise NotImplementedError

    def delete_objects(self, keys: list[str]) -> None:
        raise NotImplementedError

    def delete_folders_quietly(self, prefixes: list[str]) -> None:
        with self.sync_engine.connect() as conn:
            for prefix in prefixes:
                committed = conn.scalar(
                    text(
                        "SELECT status FROM cad_uploads WHERE source_key LIKE :prefix"
                    ),
                    {"prefix": prefix + "%"},
                )
                # deleted with its file, or failed
                assert committed in (None, "failed"), f"{prefix} deleted before commit"
        for key in list(self.sizes):
            if key.startswith(tuple(prefixes)):
                self.deleted_keys.append(key)
                del self.sizes[key]


@pytest.fixture
def sync_engine() -> Iterator[Engine]:
    engine: Engine = create_engine(URL)
    get_ograg_tables()
    with engine.begin() as conn:
        # cad_uploads first: dropping ograg_records with CASCADE would only drop its foreign key
        conn.execute(text("DROP TABLE IF EXISTS cad_uploads"))
        names = conn.execute(
            text(
                "SELECT tablename FROM pg_tables"
                " WHERE schemaname = current_schema() AND tablename LIKE 'ograg\\_%'"
            )
        ).scalars()
        for name in list(names):
            conn.execute(text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))
        ModelBase.metadata.create_all(conn)
    yield engine
    engine.dispose()


@pytest.fixture
def storage(sync_engine: Engine) -> FakeStorage:
    return FakeStorage(sync_engine)


@pytest.fixture
def client(storage: FakeStorage) -> Iterator[TestClient]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine: AsyncEngine = create_async_engine(URL)
        ontology: Ontology = load_ontology()
        app.state.sessions = create_sessionmaker(engine)
        ograg = OgRagService(
            ontology,
            PgRecordStore(
                engine,
                get_ograg_tables(),
                identity_property_names=ontology.get_identity_property_names(),
            ),
        )
        app.state.catalog = CatalogService(ograg, storage)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    register(app)
    register_service(app)
    app.include_router(v1_catalog_router)
    with TestClient(app, backend_options=SELECTOR_LOOP) as client:
        yield client


def create_machine(client: TestClient, name: str = "Robot cell") -> dict[str, Any]:
    response: Response = client.post(f"{API}/machines", json={"name": name})
    assert response.status_code == 201
    return response.json()


def create_group(client: TestClient, machine_id: str) -> dict[str, Any]:
    response: Response = client.post(
        f"{API}/machines/{machine_id}/assembly-groups",
        json={"name": "Input tray", "identifier": "AG-01"},
    )
    assert response.status_code == 201
    return response.json()


def register_file(
    client: TestClient, group_id: str, name: str = "tray.step"
) -> dict[str, Any]:
    response: Response = client.post(
        f"{API}/assembly-groups/{group_id}/cad-files",
        json={"files": [{"filename": name, "size": SIZE}]},
    )
    assert response.status_code == 201
    return response.json()[0]


def upload(storage: FakeStorage, cad_file: dict[str, Any], size: int = SIZE) -> str:
    key: str = cad_file["upload"]["fields"]["key"]
    storage.sizes[key] = size
    return key


def complete(client: TestClient, cad_file_id: str) -> Response:
    return client.post(f"{API}/cad-files/{cad_file_id}/complete")


def tree(client: TestClient) -> tuple[str, str]:
    machine_id: str = create_machine(client)["id"]
    return machine_id, create_group(client, machine_id)["id"]


def get_status(engine: Engine, cad_file_id: str) -> str | None:
    with engine.connect() as conn:
        return conn.scalar(
            text("SELECT status FROM cad_uploads WHERE cad_file_id = :id"),
            {"id": cad_file_id},
        )


def assert_problem(response: Response, status: int, error_code: str | None) -> None:
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json().get("error_code") == error_code


@pytest.fixture
def locked(sync_engine: Engine) -> Iterator[Callable[[str], None]]:
    """Locks a cad_uploads row from another connection, as the worker does, until the test ends."""
    url: str = sync_engine.url.set(drivername="postgresql").render_as_string(
        hide_password=False
    )
    with psycopg.connect(url) as conn:

        def lock(cad_file_id: str) -> None:
            conn.execute(
                "SELECT 1 FROM cad_uploads WHERE cad_file_id = %s FOR UPDATE",
                (cad_file_id,),
            )

        yield lock
        conn.rollback()


def test_machines_and_groups_can_be_created_listed_changed_and_deleted(
    client: TestClient, storage: FakeStorage
):
    machine_id: str = create_machine(client, "Robot cell")["id"]
    create_machine(client, "assembly line")
    group: dict[str, Any] = create_group(client, machine_id)

    names: list[str] = [m["name"] for m in client.get(f"{API}/machines").json()]
    assert names == ["assembly line", "Robot cell"]

    changed: Response = client.patch(
        f"{API}/machines/{machine_id}", json={"customer": "ACME", "name": "Cell"}
    )
    assert changed.status_code == 200
    assert (changed.json()["customer"], changed.json()["name"]) == ("ACME", "Cell")
    renamed: Response = client.patch(
        f"{API}/assembly-groups/{group['id']}", json={"identifier": None}
    )
    assert renamed.json()["identifier"] is None

    details: dict[str, Any] = client.get(f"{API}/machines/{machine_id}").json()
    assert details["assembly_group_count"] == 1
    assert details["status"] == "empty"
    assert [g["id"] for g in details["assembly_groups"]] == [group["id"]]

    assert client.delete(f"{API}/assembly-groups/{group['id']}").status_code == 204
    assert client.delete(f"{API}/machines/{machine_id}").status_code == 204
    assert_problem(client.get(f"{API}/machines/{machine_id}"), 404, None)
    assert_problem(client.get(f"{API}/assembly-groups/{group['id']}"), 404, None)
    assert_problem(client.post(f"{API}/machines", json={"name": " "}), 422, None)


def test_a_cad_file_is_registered_uploaded_and_completed(
    client: TestClient, storage: FakeStorage, sync_engine: Engine
):
    machine_id, group_id = tree(client)
    cad_file: dict[str, Any] = register_file(client, group_id)
    assert cad_file["name"] == "tray.step"
    assert cad_file["upload"]["url"] == "/storage/test"
    assert get_status(sync_engine, cad_file["id"]) == "uploading"
    machine: dict[str, Any] = client.get(f"{API}/machines/{machine_id}").json()
    assert (machine["status"], machine["cad_file_count"]) == ("uploading", 1)

    upload(storage, cad_file)
    completed: Response = complete(client, cad_file["id"])
    assert completed.status_code == 202
    assert completed.json()["status"] == "processing"
    # repeating it returns the current state
    assert complete(client, cad_file["id"]).json()["status"] == "processing"

    renamed: Response = client.patch(
        f"{API}/cad-files/{cad_file['id']}", json={"name": "tray-v2.step"}
    )
    assert renamed.json()["name"] == "tray-v2.step"
    assert client.get(f"{API}/cad-files/{cad_file['id']}").json()["size_bytes"] == SIZE


def test_completing_a_mismatched_upload_fails_the_file_and_deletes_its_object(
    client: TestClient, storage: FakeStorage, sync_engine: Engine
):
    _, group_id = tree(client)
    cad_file: dict[str, Any] = register_file(client, group_id)
    key: str = upload(storage, cad_file, size=SIZE + 1)

    assert_problem(complete(client, cad_file["id"]), 409, "file_mismatch")
    assert get_status(sync_engine, cad_file["id"]) == "failed"
    assert storage.deleted_keys == [key]
    # a failed file answers with its error code
    assert_problem(complete(client, cad_file["id"]), 409, "file_mismatch")


def test_completing_without_upload_is_refused(
    client: TestClient, storage: FakeStorage, sync_engine: Engine
):
    _, group_id = tree(client)
    cad_file: dict[str, Any] = register_file(client, group_id)

    assert_problem(complete(client, cad_file["id"]), 409, "upload_not_found")
    assert get_status(sync_engine, cad_file["id"]) == "uploading"
    assert_problem(complete(client, "missing"), 404, None)


def test_deleting_a_machine_deletes_its_tree_and_then_its_files(
    client: TestClient, storage: FakeStorage, sync_engine: Engine
):
    machine_id, group_id = tree(client)
    first: dict[str, Any] = register_file(client, group_id, "a.step")
    second: dict[str, Any] = register_file(client, group_id, "b.stp")
    keys: list[str] = [upload(storage, first), upload(storage, second)]

    assert client.delete(f"{API}/machines/{machine_id}").status_code == 204

    assert sorted(storage.deleted_keys) == sorted(keys)
    assert get_status(sync_engine, first["id"]) is None
    assert_problem(client.get(f"{API}/cad-files/{second['id']}"), 404, None)


def test_deleting_a_cad_file_deletes_its_object(
    client: TestClient, storage: FakeStorage, sync_engine: Engine
):
    _, group_id = tree(client)
    cad_file: dict[str, Any] = register_file(client, group_id)
    key: str = upload(storage, cad_file)

    assert client.delete(f"{API}/cad-files/{cad_file['id']}").status_code == 204
    assert storage.deleted_keys == [key]
    assert get_status(sync_engine, cad_file["id"]) is None


def test_a_file_locked_by_the_worker_answers_busy(
    client: TestClient,
    storage: FakeStorage,
    sync_engine: Engine,
    locked: Callable[[str], None],
):
    machine_id, group_id = tree(client)
    uploading: dict[str, Any] = register_file(client, group_id, "a.step")
    processing: dict[str, Any] = register_file(client, group_id, "b.step")
    upload(storage, uploading)
    upload(storage, processing)
    assert complete(client, processing["id"]).status_code == 202
    locked(uploading["id"])
    locked(processing["id"])

    assert_problem(complete(client, uploading["id"]), 409, None)
    # its state is read without waiting for the lock
    assert complete(client, processing["id"]).status_code == 202
    assert_problem(client.delete(f"{API}/cad-files/{processing['id']}"), 409, None)
    assert_problem(client.delete(f"{API}/machines/{machine_id}"), 409, None)
    assert storage.deleted_keys == []
    assert get_status(sync_engine, uploading["id"]) == "uploading"
