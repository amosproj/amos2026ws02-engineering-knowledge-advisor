"""Records routes on a scratch Postgres, with an in-memory object storage."""

import asyncio
import os
from collections.abc import AsyncGenerator, Callable, Generator, Iterator
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

from api.router_files import v1_files_router
from api.router_records import v1_records_router
from db import ModelBase, get_ograg_tables
from db.session import create_sessionmaker
from handler.exception_handler import register
from handler.service_exception_handler import register as register_service
from services.catalog import CatalogService
from services.object_storage import ObjectStorage, StoredObject
from services.ograg.ontology import Ontology
from services.ograg.service import OgRagService
from services.postgres.record_store import PgRecordStore
from services.postgres.upload_store import PgUploadStore

URL: str = os.environ.get("API_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not URL,
    reason="set API_TEST_DATABASE_URL to a scratch Postgres",
)

RECORDS_URL: str = "/api/v1/records"
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
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        engine: AsyncEngine = create_async_engine(URL)
        ontology: Ontology = load_ontology()
        app.state.sessions = create_sessionmaker(engine)
        app.state.ograg = OgRagService(
            ontology,
            PgRecordStore(
                engine,
                get_ograg_tables(),
                identity_property_names=ontology.get_identity_property_names(),
            ),
        )
        app.state.catalog = CatalogService(
            app.state.ograg, PgUploadStore(get_ograg_tables()), storage
        )
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    register(app)
    register_service(app)
    app.include_router(v1_records_router)
    app.include_router(v1_files_router)
    with TestClient(app, backend_options=SELECTOR_LOOP) as client:
        yield client


def create_record(client: TestClient, node: dict[str, Any]) -> str:
    response: Response = client.post(RECORDS_URL, json=node)
    assert response.status_code == 201
    return response.json()["id"]


def create_machine(client: TestClient, name: str = "Robot cell") -> str:
    return create_record(client, {"@type": "Machine", "name": name})


def create_group(client: TestClient, machine_id: str) -> str:
    return create_record(
        client,
        {
            "@type": "AssemblyGroup",
            "name": "Input tray",
            "identifier": "AG-01",
            "rootOf": machine_id,
        },
    )


def create_file(
    client: TestClient, machine_id: str, name: str = "cell.step"
) -> tuple[str, dict[str, Any]]:
    """Creates a CAD file record and asks for its upload form. Returns the id and the form."""
    file_id: str = create_record(
        client,
        {"@type": "CadFile", "name": name, "format": "STEP", "partOf": machine_id},
    )
    return file_id, ask_form(client, file_id).json()


def ask_form(client: TestClient, file_id: str, size: int = SIZE) -> Response:
    return client.post(f"{RECORDS_URL}/{file_id}/upload-form", json={"size": size})


def upload(storage: FakeStorage, form: dict[str, Any], size: int = SIZE) -> str:
    key: str = form["fields"]["key"]
    storage.sizes[key] = size
    return key


def complete(client: TestClient, file_id: str) -> Response:
    return client.post(f"{RECORDS_URL}/{file_id}/complete")


def get_view(client: TestClient, record_id: str) -> dict[str, Any]:
    return client.get(f"{RECORDS_URL}/{record_id}?include=status,children").json()


def tree(client: TestClient) -> tuple[str, str]:
    machine_id: str = create_machine(client)
    return machine_id, create_group(client, machine_id)


def get_status(engine: Engine, file_id: str) -> str | None:
    with engine.connect() as conn:
        return conn.scalar(
            text("SELECT status FROM cad_uploads WHERE cad_file_id = :id"),
            {"id": file_id},
        )


def assert_problem(response: Response, status: int, error_code: str | None) -> None:
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json().get("errorCode") == error_code


@pytest.fixture
def locked(sync_engine: Engine) -> Iterator[Callable[[str], None]]:
    """Locks a cad_uploads row from another connection, as the worker does, until the test ends."""
    url: str = sync_engine.url.set(drivername="postgresql").render_as_string(
        hide_password=False
    )
    with psycopg.connect(url) as conn:

        def lock(file_id: str) -> None:
            conn.execute(
                "SELECT 1 FROM cad_uploads WHERE cad_file_id = %s FOR UPDATE",
                (file_id,),
            )

        yield lock
        conn.rollback()


def test_records_can_be_created_listed_changed_and_deleted(client: TestClient):
    machine_id: str = create_machine(client, "Robot cell")
    other_id: str = create_machine(client, "assembly line")
    group_id: str = create_group(client, machine_id)

    machine_ids: list[str] = [
        rec["@id"] for rec in client.get(f"{RECORDS_URL}?cls=Machine").json()
    ]
    assert machine_ids == sorted([machine_id, other_id])

    changed: Response = client.patch(
        f"{RECORDS_URL}/{machine_id}", json={"customer": "ACME", "name": "Cell"}
    )
    assert changed.status_code == 200
    client.patch(f"{RECORDS_URL}/{group_id}", json={"identifier": None})

    view: dict[str, Any] = get_view(client, machine_id)
    assert (view["record"]["customer"], view["record"]["name"]) == ("ACME", "Cell")
    assert view["status"] == "empty"
    [group] = view["children"]
    assert group["@id"] == group_id and "identifier" not in group

    assert client.delete(f"{RECORDS_URL}/{group_id}").status_code == 200
    assert client.delete(f"{RECORDS_URL}/{machine_id}").status_code == 200
    assert_problem(client.get(f"{RECORDS_URL}/{machine_id}"), 404, None)
    assert_problem(client.get(f"{RECORDS_URL}/{group_id}"), 404, None)
    blank: Response = client.post(RECORDS_URL, json={"@type": "Machine", "name": " "})
    assert_problem(blank, 422, None)


def test_a_file_is_uploaded_with_a_form_and_completed(
    client: TestClient, storage: FakeStorage, sync_engine: Engine
):
    machine_id, _ = tree(client)
    file_id, form = create_file(client, machine_id)
    assert form["url"] == "/storage/test"
    assert get_status(sync_engine, file_id) == "uploading"
    assert get_view(client, machine_id)["status"] == "uploading"
    files: list[dict[str, Any]] = client.get(
        f"{RECORDS_URL}?parentId={machine_id}&cls=CadFile"
    ).json()
    assert [rec["@id"] for rec in files] == [file_id]

    upload(storage, form)
    completed: Response = complete(client, file_id)
    assert completed.status_code == 202
    assert (completed.json()["status"], completed.json()["sizeBytes"]) == (
        "processing",
        SIZE,
    )
    # repeating it returns the current state
    assert complete(client, file_id).json()["status"] == "processing"
    assert_problem(ask_form(client, file_id), 409, "upload_exists")

    renamed: Response = client.patch(
        f"{RECORDS_URL}/{file_id}", json={"name": "tray-v2.step"}
    )
    assert renamed.status_code == 200
    assert get_view(client, file_id)["status"] == "processing"


def test_completing_a_mismatched_upload_fails_the_file_and_deletes_its_object(
    client: TestClient, storage: FakeStorage, sync_engine: Engine
):
    machine_id, _ = tree(client)
    file_id, form = create_file(client, machine_id)
    key: str = upload(storage, form, size=SIZE + 1)

    assert_problem(complete(client, file_id), 409, "file_mismatch")
    assert get_status(sync_engine, file_id) == "failed"
    assert storage.deleted_keys == [key]
    # a failed file answers with its error code
    assert_problem(complete(client, file_id), 409, "file_mismatch")

    # and can be uploaded again
    assert ask_form(client, file_id).status_code == 200
    upload(storage, form)
    assert complete(client, file_id).status_code == 202


def test_completing_without_upload_is_refused(
    client: TestClient, storage: FakeStorage, sync_engine: Engine
):
    machine_id, group_id = tree(client)
    file_id: str = create_record(
        client, {"@type": "CadFile", "name": "cell.step", "partOf": machine_id}
    )
    assert_problem(complete(client, file_id), 409, "upload_not_found")
    ask_form(client, file_id)

    assert_problem(complete(client, file_id), 409, "upload_not_found")
    assert get_status(sync_engine, file_id) == "uploading"
    assert_problem(complete(client, "missing"), 404, None)
    assert_problem(complete(client, group_id), 422, None)


def test_deleting_a_machine_deletes_its_tree_and_then_its_files(
    client: TestClient, storage: FakeStorage, sync_engine: Engine
):
    machine_id, group_id = tree(client)
    file_id, form = create_file(client, machine_id, "a.step")
    key: str = upload(storage, form)

    deleted: Response = client.delete(f"{RECORDS_URL}/{machine_id}")
    assert deleted.status_code == 200
    assert sorted(deleted.json()["deletedIds"]) == sorted(
        [machine_id, group_id, file_id]
    )

    assert storage.deleted_keys == [key]
    assert get_status(sync_engine, file_id) is None
    assert_problem(client.get(f"{RECORDS_URL}/{file_id}"), 404, None)


def test_a_machine_takes_one_cad_file(client: TestClient):
    machine_id: str = create_machine(client)
    file_id, _ = create_file(client, machine_id)
    second: Response = client.post(
        RECORDS_URL,
        json={"@type": "CadFile", "name": "b.step", "partOf": machine_id},
    )
    assert_problem(second, 409, "max_per_parent")
    assert [rec["@id"] for rec in client.get(f"{RECORDS_URL}?cls=CadFile").json()] == [
        file_id
    ]


def test_deleting_a_file_record_deletes_its_object(
    client: TestClient, storage: FakeStorage, sync_engine: Engine
):
    machine_id, _ = tree(client)
    file_id, form = create_file(client, machine_id)
    key: str = upload(storage, form)

    assert client.delete(f"{RECORDS_URL}/{file_id}").status_code == 200
    assert storage.deleted_keys == [key]
    assert get_status(sync_engine, file_id) is None


def test_a_file_locked_by_the_worker_answers_busy(
    client: TestClient,
    storage: FakeStorage,
    sync_engine: Engine,
    locked: Callable[[str], None],
):
    machine_id, _ = tree(client)
    uploading_id, uploading_form = create_file(
        client, create_machine(client, "Other cell"), "a.step"
    )
    processing_id, processing_form = create_file(client, machine_id, "b.step")
    upload(storage, uploading_form)
    upload(storage, processing_form)
    assert complete(client, processing_id).status_code == 202
    locked(uploading_id)
    locked(processing_id)

    assert_problem(complete(client, uploading_id), 409, None)
    assert_problem(ask_form(client, uploading_id), 409, None)
    # its state is read without waiting for the lock
    assert complete(client, processing_id).status_code == 202
    assert_problem(client.delete(f"{RECORDS_URL}/{processing_id}"), 409, None)
    assert_problem(client.delete(f"{RECORDS_URL}/{machine_id}"), 409, None)
    assert storage.deleted_keys == []
    assert get_status(sync_engine, uploading_id) == "uploading"


def test_the_tree_and_the_ancestors_read_every_level_from_postgres(
    client: TestClient, storage: FakeStorage
):
    machine_id, group_id = tree(client)
    inner_id: str = create_record(
        client, {"@type": "AssemblyGroup", "name": "Gripper", "partOf": group_id}
    )
    file_id, form = create_file(client, machine_id)
    upload(storage, form)
    complete(client, file_id)

    machine: dict[str, Any] = client.get(f"{RECORDS_URL}/{machine_id}/tree").json()
    by_id: dict[str, dict[str, Any]] = {
        child["record"]["@id"]: child for child in machine["children"]
    }
    assert set(by_id) == {group_id, file_id}
    assert by_id[file_id]["status"] == "processing"
    assert "status" not in by_id[group_id]
    [inner] = by_id[group_id]["children"]
    assert (inner["record"]["@id"], inner["children"]) == (inner_id, [])

    ancestors: dict[str, Any] = client.get(f"{RECORDS_URL}/{inner_id}/ancestors").json()
    [group] = ancestors["parents"]
    [top] = group["parents"]
    assert (group["record"]["@id"], top["record"]["@id"]) == (group_id, machine_id)


def test_a_write_with_an_old_version_is_refused(client: TestClient):
    machine_id: str = create_machine(client)
    read: Response = client.get(f"{RECORDS_URL}/{machine_id}")
    renamed: Response = client.patch(
        f"{RECORDS_URL}/{machine_id}",
        json={"name": "Cell 2"},
        headers={"If-Match": read.headers["ETag"]},
    )
    assert renamed.status_code == 200
    # the version a write returns is the one readers see after the commit
    current: str = client.get(f"{RECORDS_URL}/{machine_id}").headers["ETag"]
    assert renamed.headers["ETag"] == current != read.headers["ETag"]
    stale: Response = client.patch(
        f"{RECORDS_URL}/{machine_id}",
        json={"name": "Cell 3"},
        headers={"If-Match": read.headers["ETag"]},
    )
    assert (stale.status_code, stale.headers["content-type"]) == (412, PROBLEM_JSON)
