import asyncio
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

import pytest
from fakes import make_service
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import assert_mentions
from httpx2 import Response

from api.router_records import get_author, v1_records_router
from db.session import get_session
from handler.exception_handler import register
from handler.service_exception_handler import register as register_service
from services import ConflictError, Record, Tx
from services.ograg.service import DeleteResult, OgRagService

PROBLEM_JSON: str = "application/problem+json"
SESSION: str = "the request's session"
RECORDS_URL: str = "/api/v1/records"
MACHINE_ID: str = "RC-01"
GROUP_ID: str = "AG-1"
ITEM_ID: str = "KI-1"
AUTHOR: str = "Jane"
MACHINE: dict[str, Any] = {
    "@type": "Machine",
    "identifier": MACHINE_ID,
    "name": "Robot cell",
}
GROUP: dict[str, Any] = {
    "@type": "AssemblyGroup",
    "name": "Input tray",
    "partOf": MACHINE_ID,
}
ITEM: dict[str, Any] = {
    "@type": "KnowledgeItem",
    "statement": "Chamfer the nest.",
}
LINKED_ITEM: dict[str, Any] = {**ITEM, "appliesTo": [GROUP_ID]}


@pytest.fixture
def service() -> OgRagService:
    return make_service()


@pytest.fixture
def app(service: OgRagService) -> FastAPI:
    app = FastAPI()
    register(app)
    register_service(app)
    app.include_router(v1_records_router)
    app.state.ograg = service

    async def session() -> AsyncIterator[str]:
        yield SESSION

    app.dependency_overrides[get_session] = session
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def seed_machine_and_group(service: OgRagService) -> None:
    """Machines and groups cannot be written through /records."""

    async def seed() -> None:
        await service.upsert_record(MACHINE_ID, MACHINE)
        await service.upsert_record(GROUP_ID, GROUP)

    asyncio.run(seed())


def put_record(client: TestClient, record_id: str, node: dict[str, Any]) -> Response:
    return client.put(f"{RECORDS_URL}/{record_id}", json=node)


def delete_record(client: TestClient, record_id: str, query: str = "") -> Response:
    return client.delete(f"{RECORDS_URL}/{record_id}{query}")


def get_listed_records(client: TestClient) -> dict[str, Any]:
    return client.get(RECORDS_URL).json()


def assert_problem(response: Response, status: int, *keywords: str) -> None:
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM_JSON
    body: dict[str, Any] = response.json()
    assert body["status"] == status and body["instance"] == response.request.url.path
    assert_mentions(body["detail"], *keywords)


def test_put_list_and_delete(client: TestClient, service: OgRagService):
    seed_machine_and_group(service)
    response: Response = put_record(client, ITEM_ID, {**ITEM, "colour": "red"})
    written: dict[str, Any] = response.json()
    assert written["id"] == ITEM_ID and len(written["warnings"]) == 1
    assert_mentions(written["warnings"][0], "KnowledgeItem", "colour")
    assert put_record(client, "KI-2", LINKED_ITEM).status_code == 200
    records: dict[str, Any] = get_listed_records(client)
    assert sorted(records) == [GROUP_ID, ITEM_ID, "KI-2", MACHINE_ID]
    assert records["KI-2"]["appliesTo"] == [GROUP_ID]

    assert delete_record(client, ITEM_ID).json() == {
        "deleted_ids": [ITEM_ID],
        "marked_ids": [],
    }
    assert ITEM_ID not in get_listed_records(client)


def test_a_record_is_listed_as_stored(client: TestClient):
    put_record(client, ITEM_ID, ITEM)
    assert get_listed_records(client) == {ITEM_ID: {**ITEM, "@id": ITEM_ID}}


def test_one_record_is_read_with_its_link_ids(
    client: TestClient, service: OgRagService
):
    seed_machine_and_group(service)
    put_record(client, ITEM_ID, LINKED_ITEM)
    response: Response = client.get(f"{RECORDS_URL}/{ITEM_ID}")
    assert response.status_code == 200
    assert response.json() == {**LINKED_ITEM, "@id": ITEM_ID}


def test_reading_a_missing_record_is_a_404_problem(client: TestClient):
    assert_problem(client.get(f"{RECORDS_URL}/{ITEM_ID}"), 404)


def test_the_review_list_is_not_read_as_a_record_id(client: TestClient):
    response: Response = client.get(f"{RECORDS_URL}/review")
    assert response.status_code == 200 and response.json() == []


def test_plain_type_and_id_keys_are_ordinary_properties(client: TestClient):
    response: Response = put_record(
        client, ITEM_ID, {**ITEM, "type": "robot", "id": "x"}
    )
    warnings: list[str] = response.json()["warnings"]
    assert len(warnings) == 2
    assert_mentions(" ".join(warnings), "KnowledgeItem.type", "KnowledgeItem.id")
    assert get_listed_records(client)[ITEM_ID]["@type"] == ITEM["@type"]


def test_a_body_that_is_not_an_object_is_a_422_problem(client: TestClient):
    response: Response = client.put(f"{RECORDS_URL}/{ITEM_ID}", json=[ITEM])
    assert response.status_code == 422


def test_the_api_docs_name_the_record_models(app: FastAPI):
    schemas: dict[str, Any] = app.openapi()["components"]["schemas"]
    assert any(name.startswith("RecordNode") for name in schemas)
    assert "Records" in schemas


def test_a_record_that_does_not_fit_is_a_422_problem(client: TestClient):
    characteristic: dict[str, Any] = {
        "@type": "Characteristic",
        "function": "Feed parts",
    }
    assert_problem(put_record(client, "L-1", characteristic), 422, "Characteristic")
    assert get_listed_records(client) == {}


def test_a_link_to_a_missing_record_is_a_422_problem(client: TestClient):
    assert_problem(put_record(client, ITEM_ID, LINKED_ITEM), 422, "appliesTo", GROUP_ID)


def test_text_the_database_cannot_store_is_a_422_problem(client: TestClient):
    item: dict[str, Any] = {**ITEM, "statement": "nul \u0000 byte"}
    assert_problem(put_record(client, ITEM_ID, item), 422)
    assert get_listed_records(client) == {}


def test_a_conflict_is_a_409_problem(client: TestClient, service: OgRagService):
    async def conflicting_save(records: Sequence[Record], tx: Tx | None = None) -> None:
        raise ConflictError("deadlock: try again")

    service.store.save_records = conflicting_save  # type: ignore[method-assign]
    assert_problem(put_record(client, ITEM_ID, ITEM), 409, "deadlock")


def test_machines_groups_and_cad_files_are_not_written_here(
    client: TestClient, service: OgRagService
):
    assert_problem(put_record(client, MACHINE_ID, MACHINE), 409, "own endpoints")
    # without @type, a record is an assembly group
    assert_problem(put_record(client, GROUP_ID, {"name": "x"}), 409, "own endpoints")
    seed_machine_and_group(service)
    assert_problem(delete_record(client, MACHINE_ID), 409, "own endpoints")
    assert MACHINE_ID in get_listed_records(client)


def test_deleting_a_missing_record_is_a_404_problem(client: TestClient):
    assert_problem(delete_record(client, ITEM_ID), 404)


def test_an_invalid_record_id_is_a_422_problem(client: TestClient):
    assert_problem(put_record(client, "-bad id", ITEM), 422)


def test_review_lists_records_that_lost_their_last_link(
    client: TestClient, service: OgRagService
):
    seed_machine_and_group(service)
    put_record(client, ITEM_ID, LINKED_ITEM)
    asyncio.run(service.delete_record(GROUP_ID))
    reviews: list[dict[str, Any]] = client.get(f"{RECORDS_URL}/review").json()
    assert [rec["id"] for rec in reviews] == [ITEM_ID]
    assert_mentions(reviews[0]["review"], "AssemblyGroup", GROUP_ID)


def test_delete_passes_its_options_and_returns_the_marked_ids(
    client: TestClient, service: OgRagService
):
    calls: list[tuple[str, Tx | None, bool]] = []

    async def spy_delete(
        record_id: str, tx: Tx | None = None, delete_orphans: bool = False
    ) -> DeleteResult:
        calls.append((record_id, tx, delete_orphans))
        return DeleteResult(deleted_ids=[record_id], marked_ids=["KI-2"])

    service.delete_record = spy_delete  # type: ignore[method-assign]
    response: Response = delete_record(client, ITEM_ID, "?delete_orphans=true")
    assert calls == [(ITEM_ID, SESSION, True)]
    assert response.json() == {"deleted_ids": [ITEM_ID], "marked_ids": ["KI-2"]}


def test_writes_run_in_the_requests_session(client: TestClient, service: OgRagService):
    seen: list[Tx | None] = []
    save = service.store.save_records

    async def recording_save(records: Sequence[Record], tx: Tx | None = None) -> None:
        seen.append(tx)
        await save(records, tx)

    service.store.save_records = recording_save  # type: ignore[method-assign]
    put_record(client, ITEM_ID, ITEM)
    assert seen == [SESSION]


def test_the_author_comes_from_get_author(app: FastAPI, client: TestClient):
    item: dict[str, Any] = {"@type": "KnowledgeItem", "statement": "x", "author": "x"}
    app.dependency_overrides[get_author] = lambda: AUTHOR
    put_record(client, ITEM_ID, item)
    assert get_listed_records(client)[ITEM_ID]["author"] == AUTHOR
