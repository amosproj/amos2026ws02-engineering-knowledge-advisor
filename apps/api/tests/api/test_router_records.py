import asyncio
from collections.abc import AsyncGenerator, Iterator, Sequence
from typing import Any

import pytest
from fakes import MemoryStorage, make_catalog, make_service
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import assert_mentions
from httpx2 import Response

from api.router_files import v1_files_router
from api.router_records import v1_records_router
from db.session import get_session
from handler.exception_handler import register
from handler.service_exception_handler import register as register_service
from services import ConflictError, Record, Tx
from services.catalog import CatalogService
from services.object_storage import ObjectStorageError
from services.ograg.service import DeleteResult, OgRagService
from services.uploads import Upload

PROBLEM_JSON: str = "application/problem+json"
FASTAPI_DEFAULT_200: str = (
    "Successful Response"  # description FastAPI uses if none is given
)
SESSION: str = "the request's session"
RECORDS_URL: str = "/api/v1/records"
MACHINE_ID: str = "RC-01"
GROUP_ID: str = "AG-1"
ITEM_ID: str = "KI-1"
OTHER_ITEM_ID: str = "KI-2"
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
ITEM: dict[str, Any] = {
    "@type": "KnowledgeItem",
    # validation types a nested node, sending its @type keeps the stored record equal to this
    "properties": {
        "@type": "KnowledgeProperties",
        "name": "Chamfer",
        "statement": "Chamfer the nest.",
    },
}
LINKED_ITEM: dict[str, Any] = {**ITEM, "appliesTo": [GROUP_ID]}
CAD_FILE: dict[str, Any] = {
    "@type": "CadFile",
    "name": "cell.step",
    "partOf": MACHINE_ID,
}


@pytest.fixture
def service() -> OgRagService:
    return make_service()


@pytest.fixture
def catalog(service: OgRagService) -> CatalogService:
    return make_catalog(service)


@pytest.fixture
def app(service: OgRagService, catalog: CatalogService) -> FastAPI:
    app = FastAPI()
    register(app)
    register_service(app)
    app.include_router(v1_records_router)
    app.include_router(v1_files_router)
    app.state.ograg = service
    app.state.catalog = catalog

    async def session() -> AsyncGenerator[str]:
        yield SESSION

    app.dependency_overrides[get_session] = session
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def seed_machine_and_group(service: OgRagService) -> None:
    """Writes a machine and its assembly group through the service."""

    async def seed() -> None:
        await service.upsert_record(MACHINE_ID, MACHINE)
        await service.upsert_record(GROUP_ID, GROUP)

    asyncio.run(seed())


def put_record(client: TestClient, record_id: str, node: dict[str, Any]) -> Response:
    return client.put(f"{RECORDS_URL}/{record_id}", json=node)


def delete_record(client: TestClient, record_id: str, query: str = "") -> Response:
    return client.delete(f"{RECORDS_URL}/{record_id}{query}")


def get_all_records(client: TestClient) -> list[dict[str, Any]]:
    return client.get(RECORDS_URL).json()


def drop_versions(value: object) -> object:
    """Returns ``value`` without ``version`` keys, at any depth."""
    if isinstance(value, dict):
        return {k: drop_versions(v) for k, v in value.items() if k != "version"}
    if isinstance(value, list):
        return [drop_versions(item) for item in value]
    return value


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
    assert put_record(client, OTHER_ITEM_ID, LINKED_ITEM).status_code == 200
    assert get_all_records(client) == [
        {**GROUP, "@id": GROUP_ID},
        {**ITEM, "@id": ITEM_ID},
        {**LINKED_ITEM, "@id": OTHER_ITEM_ID},
        {**MACHINE, "@id": MACHINE_ID},
    ]

    assert delete_record(client, ITEM_ID).json() == {
        "deletedIds": [ITEM_ID],
        "markedIds": [],
    }
    assert get_all_records(client) == [
        {**GROUP, "@id": GROUP_ID},
        {**LINKED_ITEM, "@id": OTHER_ITEM_ID},
        {**MACHINE, "@id": MACHINE_ID},
    ]


def test_records_return_as_list_sorted_by_id(client: TestClient, service: OgRagService):
    seed_machine_and_group(service)
    put_record(client, ITEM_ID, ITEM)
    records: list[dict[str, Any]] = get_all_records(client)
    assert [rec["@id"] for rec in records] == [GROUP_ID, ITEM_ID, MACHINE_ID]


def test_a_record_is_listed_as_stored(client: TestClient):
    put_record(client, ITEM_ID, ITEM)
    assert get_all_records(client) == [{**ITEM, "@id": ITEM_ID}]


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
    [item] = get_all_records(client)
    assert item["@type"] == ITEM["@type"]


def test_a_body_that_is_not_an_object_is_a_422_problem(client: TestClient):
    response: Response = client.put(f"{RECORDS_URL}/{ITEM_ID}", json=[ITEM])
    assert response.status_code == 422


def test_the_api_docs_name_the_record_models(app: FastAPI):
    schemas: dict[str, Any] = app.openapi()["components"]["schemas"]
    assert any(name.startswith("RecordNode") for name in schemas)
    assert "Records" in schemas


def test_every_records_route_documents_its_success_response(app: FastAPI):
    paths: dict[str, Any] = app.openapi()["paths"]
    for path, operations in paths.items():
        for method, operation in operations.items():
            [success] = [
                response
                for code, response in operation["responses"].items()
                if code.startswith("2")
            ]
            assert success["description"] != FASTAPI_DEFAULT_200, f"{method} {path}"


def test_a_record_that_does_not_fit_is_a_422_problem(client: TestClient):
    group_properties: dict[str, Any] = {
        "@type": "AssemblyProperties",
        "path": "/tray",
    }
    assert_problem(
        put_record(client, "P-1", group_properties), 422, "AssemblyProperties"
    )
    assert get_all_records(client) == []


def test_a_link_to_a_missing_record_is_a_422_problem(client: TestClient):
    assert_problem(put_record(client, ITEM_ID, LINKED_ITEM), 422, "appliesTo", GROUP_ID)


def test_text_the_database_cannot_store_is_a_422_problem(client: TestClient):
    item: dict[str, Any] = {**ITEM, "properties": {"name": "nul \u0000 byte"}}
    assert_problem(put_record(client, ITEM_ID, item), 422)
    assert get_all_records(client) == []


def test_a_conflict_is_a_409_problem(client: TestClient, service: OgRagService):
    async def conflicting_save(records: Sequence[Record], tx: Tx | None = None) -> None:
        raise ConflictError("deadlock: try again")

    service.store.save_records = conflicting_save  # type: ignore[method-assign]
    assert_problem(put_record(client, ITEM_ID, ITEM), 409, "deadlock")


def test_deleting_a_parent_deletes_its_dependents_and_marks_the_rest(
    client: TestClient,
):
    assert put_record(client, MACHINE_ID, MACHINE).status_code == 200
    assert put_record(client, GROUP_ID, GROUP).status_code == 200
    put_record(client, ITEM_ID, LINKED_ITEM)

    assert delete_record(client, MACHINE_ID).json() == {
        "deletedIds": [GROUP_ID, MACHINE_ID],
        "markedIds": [ITEM_ID],
    }
    assert [rec["@id"] for rec in get_all_records(client)] == [ITEM_ID]


def test_post_creates_a_record_with_a_generated_id(client: TestClient):
    response: Response = client.post(RECORDS_URL, json={**MACHINE, "@id": "ignored"})
    assert response.status_code == 201
    record_id: str = response.json()["id"]
    assert record_id != "ignored"
    assert client.get(f"{RECORDS_URL}/{record_id}").json() == {
        **MACHINE,
        "@id": record_id,
    }
    assert_problem(client.post(RECORDS_URL, json={"@type": "Machine"}), 422)


def test_patch_changes_only_the_sent_literal_properties(
    client: TestClient, service: OgRagService
):
    seed_machine_and_group(service)
    response: Response = client.patch(
        f"{RECORDS_URL}/{GROUP_ID}", json={"name": " Tray ", "identifier": "AG-1"}
    )
    assert response.status_code == 200
    assert drop_versions(
        client.patch(f"{RECORDS_URL}/{GROUP_ID}", json={"identifier": None}).json()
    ) == {"id": GROUP_ID, "warnings": []}
    stored: dict[str, Any] = client.get(f"{RECORDS_URL}/{GROUP_ID}").json()
    assert stored == {**GROUP, "name": "Tray", "@id": GROUP_ID}

    unknown: Response = client.patch(
        f"{RECORDS_URL}/{GROUP_ID}", json={"colour": "red"}
    )
    assert_problem(unknown, 422, "colour")
    # a merge patch may change links too, sent with its own media type
    put_record(client, ITEM_ID, LINKED_ITEM)
    moved: Response = client.patch(
        f"{RECORDS_URL}/{ITEM_ID}",
        content='{"appliesTo": null, "appliesToMachine": ["RC-01"]}',
        headers={"Content-Type": "application/merge-patch+json"},
    )
    assert moved.status_code == 200
    item: dict[str, Any] = client.get(f"{RECORDS_URL}/{ITEM_ID}").json()
    assert (item.get("appliesTo"), item["appliesToMachine"]) == (None, [MACHINE_ID])
    assert_problem(client.patch(f"{RECORDS_URL}/missing", json={"name": "x"}), 404)


@pytest.mark.parametrize(
    ("if_match", "status"),
    [
        ("{etag}", 200),
        ("*", 200),
        ('"other", {etag}', 200),
        ("W/{etag}", 412),
        ('"other"', 412),
    ],
    ids=["current", "any", "list with current", "weak", "other"],
)
def test_if_match_lets_a_write_through_only_with_the_current_version(
    client: TestClient, service: OgRagService, if_match: str, status: int
):
    seed_machine_and_group(service)
    etag: str = client.get(f"{RECORDS_URL}/{GROUP_ID}").headers["ETag"]
    response: Response = client.patch(
        f"{RECORDS_URL}/{GROUP_ID}",
        json={"name": "Tray"},
        headers={"If-Match": if_match.format(etag=etag)},
    )
    assert response.status_code == status


def test_a_write_with_an_old_version_is_refused(
    client: TestClient, service: OgRagService
):
    seed_machine_and_group(service)
    old_etag: str = client.get(f"{RECORDS_URL}/{GROUP_ID}").headers["ETag"]
    # someone else saves in between
    renamed: Response = client.patch(f"{RECORDS_URL}/{GROUP_ID}", json={"name": "Tray"})
    assert renamed.headers["ETag"] == f'"{renamed.json()["version"]}"' != old_etag
    stale: dict[str, str] = {"If-Match": old_etag}
    for response in [
        client.patch(f"{RECORDS_URL}/{GROUP_ID}", json={"name": "Old"}, headers=stale),
        client.put(f"{RECORDS_URL}/{GROUP_ID}", json=GROUP, headers=stale),
        client.delete(f"{RECORDS_URL}/{GROUP_ID}", headers=stale),
    ]:
        assert_problem(response, 412, GROUP_ID)
    assert client.get(f"{RECORDS_URL}/{GROUP_ID}").json()["name"] == "Tray"
    # If-Match on a record that doesn't exist yet never matches
    missing: Response = client.put(
        f"{RECORDS_URL}/AG-2", json=GROUP, headers={"If-Match": "*"}
    )
    assert_problem(missing, 412, "AG-2")
    # the views carry the same version as the ETag
    view: dict[str, Any] = client.get(
        f"{RECORDS_URL}/{GROUP_ID}?include=children"
    ).json()
    tree: dict[str, Any] = client.get(f"{RECORDS_URL}/{GROUP_ID}/tree").json()
    assert view["version"] == tree["version"] == renamed.json()["version"]


def test_records_are_filtered_by_class_and_parent(
    client: TestClient, service: OgRagService
):
    seed_machine_and_group(service)
    put_record(client, ITEM_ID, LINKED_ITEM)
    put_record(client, "CF-1", CAD_FILE)

    def get_ids(query: str) -> list[str]:
        return [rec["@id"] for rec in client.get(f"{RECORDS_URL}?{query}").json()]

    assert get_ids("cls=Machine") == [MACHINE_ID]
    assert get_ids(f"parentId={GROUP_ID}") == [ITEM_ID]
    assert get_ids(f"parentId={MACHINE_ID}") == [GROUP_ID, "CF-1"]
    assert get_ids(f"parentId={MACHINE_ID}&cls=CadFile") == ["CF-1"]
    assert get_ids("parentId=missing") == []


def test_include_wraps_each_record_with_its_status_and_children(
    client: TestClient, service: OgRagService
):
    seed_machine_and_group(service)
    put_record(client, "CF-1", CAD_FILE)

    machines: list[dict[str, Any]] = client.get(
        f"{RECORDS_URL}?cls=Machine&include=status,children"
    ).json()
    assert drop_versions(machines) == [
        {
            "record": {**MACHINE, "@id": MACHINE_ID},
            "status": "empty",
            "children": [{**GROUP, "@id": GROUP_ID}, {**CAD_FILE, "@id": "CF-1"}],
        }
    ]
    # null before the first upload
    assert client.get(f"{RECORDS_URL}/CF-1?include=upload").json()["upload"] is None

    client.post(f"{RECORDS_URL}/CF-1/upload-form", json={"size": 300})
    group: dict[str, Any] = client.get(
        f"{RECORDS_URL}/{GROUP_ID}?include=status"
    ).json()
    # no status: groups neither carry a file nor are pointed at by file records
    assert drop_versions(group) == {"record": {**GROUP, "@id": GROUP_ID}}
    cad_file: dict[str, Any] = client.get(
        f"{RECORDS_URL}/CF-1?include=status,upload"
    ).json()
    assert (cad_file["status"], cad_file["upload"]["sizeBytes"]) == ("uploading", 300)
    machine: dict[str, Any] = client.get(
        f"{RECORDS_URL}/{MACHINE_ID}?include=children,status,upload"
    ).json()
    # file records are children too, sorted by id
    assert (machine["status"], [child["@id"] for child in machine["children"]]) == (
        "uploading",
        [GROUP_ID, "CF-1"],
    )
    # the upload only for file records
    assert "upload" not in machine
    children_only: list[dict[str, Any]] = client.get(
        f"{RECORDS_URL}?cls=Machine&include=children"
    ).json()
    assert [set(view) for view in children_only] == [{"record", "version", "children"}]
    # an empty list is still sent when asked for
    groups: list[dict[str, Any]] = client.get(
        f"{RECORDS_URL}?cls=AssemblyGroup&include=children"
    ).json()
    assert groups[0]["children"] == []


def test_a_list_reads_its_includes_once_for_all_records(
    client: TestClient,
    service: OgRagService,
    catalog: CatalogService,
    monkeypatch: pytest.MonkeyPatch,
):
    for number in range(3):
        put_record(client, f"RC-{number}", {**MACHINE, "identifier": f"RC-{number}"})
        put_record(client, f"CF-{number}", {**CAD_FILE, "partOf": f"RC-{number}"})
    client.post(f"{RECORDS_URL}/CF-1/upload-form", json={"size": 300})
    calls: list[str] = []
    get_linking_records = service.store.get_linking_records
    get_uploads = catalog.uploads.get_uploads

    async def count_linking(target_ids: Sequence[str], tx: Tx) -> list[Record]:
        calls.append("get_linking_records")
        return await get_linking_records(target_ids, tx)

    async def count_uploads(file_ids: Sequence[str], tx: Tx) -> dict[str, Upload]:
        calls.append("get_uploads")
        return await get_uploads(file_ids, tx)

    monkeypatch.setattr(service.store, "get_linking_records", count_linking)
    monkeypatch.setattr(catalog.uploads, "get_uploads", count_uploads)

    machines: list[dict[str, Any]] = client.get(
        f"{RECORDS_URL}?cls=Machine&include=status,children,upload"
    ).json()
    assert [view["status"] for view in machines] == ["empty", "uploading", "empty"]
    assert [view["children"][0]["@id"] for view in machines] == ["CF-0", "CF-1", "CF-2"]
    # one read for the children of the status, one for the included children
    assert sorted(calls) == ["get_linking_records"] * 2 + ["get_uploads"]


def test_the_tree_nests_every_record_below_and_gives_files_a_status(
    client: TestClient, service: OgRagService
):
    seed_machine_and_group(service)
    put_record(client, "CF-1", CAD_FILE)
    put_record(client, ITEM_ID, LINKED_ITEM)

    tree: dict[str, Any] = client.get(f"{RECORDS_URL}/{MACHINE_ID}/tree").json()
    assert drop_versions(tree) == {
        "record": {**MACHINE, "@id": MACHINE_ID},
        "status": "empty",
        "children": [
            {
                "record": {**GROUP, "@id": GROUP_ID},
                "children": [
                    {"record": {**LINKED_ITEM, "@id": ITEM_ID}, "children": []}
                ],
            },
            {
                "record": {**CAD_FILE, "@id": "CF-1"},
                "status": "empty",
                "upload": None,
                "children": [],
            },
        ],
    }

    client.post(f"{RECORDS_URL}/CF-1/upload-form", json={"size": 300})
    shallow: dict[str, Any] = client.get(
        f"{RECORDS_URL}/{MACHINE_ID}/tree?depth=1"
    ).json()
    assert [child["children"] for child in shallow["children"]] == [[], []]
    assert (shallow["status"], shallow["children"][1]["upload"]["sizeBytes"]) == (
        "uploading",
        300,
    )
    assert_problem(client.get(f"{RECORDS_URL}/missing/tree"), 404)
    assert_problem(client.get(f"{RECORDS_URL}/{MACHINE_ID}/tree?depth=0"), 422)


def test_the_ancestors_lead_from_a_record_up_to_its_machine(
    client: TestClient, service: OgRagService
):
    seed_machine_and_group(service)
    put_record(client, "CF-1", CAD_FILE)
    put_record(client, ITEM_ID, LINKED_ITEM)
    machine: dict[str, Any] = {
        "record": {**MACHINE, "@id": MACHINE_ID},
        "status": "empty",
        "parents": [],
    }

    item: dict[str, Any] = client.get(f"{RECORDS_URL}/{ITEM_ID}/ancestors").json()
    assert drop_versions(item) == {
        "record": {**LINKED_ITEM, "@id": ITEM_ID},
        "parents": [{"record": {**GROUP, "@id": GROUP_ID}, "parents": [machine]}],
    }
    cad_file: dict[str, Any] = client.get(f"{RECORDS_URL}/CF-1/ancestors").json()
    assert (
        cad_file["status"],
        cad_file["upload"],
        drop_versions(cad_file["parents"]),
    ) == (
        "empty",
        None,
        [machine],
    )
    near: dict[str, Any] = client.get(
        f"{RECORDS_URL}/{ITEM_ID}/ancestors?depth=1"
    ).json()
    assert near["parents"][0]["parents"] == []
    assert_problem(client.get(f"{RECORDS_URL}/missing/ancestors"), 404)


def test_an_unknown_include_is_a_422_problem(client: TestClient):
    assert_problem(client.get(f"{RECORDS_URL}?include=status,count"), 422)
    assert_problem(client.get(f"{RECORDS_URL}?include="), 422)


def test_a_file_record_is_uploaded_with_a_form_and_completed(
    client: TestClient, service: OgRagService, catalog: CatalogService
):
    seed_machine_and_group(service)
    put_record(client, "CF-1", CAD_FILE)
    storage = catalog.storage
    assert isinstance(storage, MemoryStorage)

    not_asked: Response = client.post(f"{RECORDS_URL}/CF-1/complete")
    assert not_asked.status_code == 409
    assert not_asked.json()["errorCode"] == "upload_not_found"

    form: Response = client.post(f"{RECORDS_URL}/CF-1/upload-form", json={"size": 300})
    assert form.status_code == 200
    storage.sizes[form.json()["fields"]["key"]] = 300
    completed: Response = client.post(f"{RECORDS_URL}/CF-1/complete")
    assert completed.status_code == 202
    assert (completed.json()["id"], completed.json()["status"]) == (
        "CF-1",
        "processing",
    )

    again: Response = client.post(f"{RECORDS_URL}/CF-1/upload-form", json={"size": 1})
    assert again.status_code == 409
    assert again.json()["errorCode"] == "upload_exists"


def test_an_unreachable_storage_is_a_503_problem(
    client: TestClient, service: OgRagService, catalog: CatalogService
):
    seed_machine_and_group(service)
    put_record(client, "CF-1", CAD_FILE)
    client.post(f"{RECORDS_URL}/CF-1/upload-form", json={"size": 300})

    def fail(key: str) -> int | None:
        raise ObjectStorageError("Could not connect to http://minio:9000")

    catalog.storage.get_object_size = fail  # type: ignore[method-assign]
    response: Response = client.post(f"{RECORDS_URL}/CF-1/complete")
    assert_problem(response, 503, "storage")
    assert "minio" not in response.json()["detail"]


def test_only_a_file_record_gets_an_upload_form(
    client: TestClient, service: OgRagService
):
    seed_machine_and_group(service)
    no_file: Response = client.post(
        f"{RECORDS_URL}/{MACHINE_ID}/upload-form", json={"size": 300}
    )
    assert_problem(no_file, 422, "Machine")
    assert_problem(
        client.post(f"{RECORDS_URL}/missing/upload-form", json={"size": 300}), 404
    )
    put_record(client, "CF-1", CAD_FILE)
    assert_problem(
        client.post(f"{RECORDS_URL}/CF-1/upload-form", json={"size": 0}), 422
    )


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
        return DeleteResult(deleted_ids=[record_id], marked_ids=[OTHER_ITEM_ID])

    put_record(client, ITEM_ID, ITEM)
    service.delete_record = spy_delete  # type: ignore[method-assign]
    response: Response = delete_record(client, ITEM_ID, "?deleteOrphans=true")
    assert calls == [(ITEM_ID, SESSION, True)]
    assert response.json() == {"deletedIds": [ITEM_ID], "markedIds": [OTHER_ITEM_ID]}


def test_writes_run_in_the_requests_session(client: TestClient, service: OgRagService):
    seen: list[Tx | None] = []
    save = service.store.save_records

    async def recording_save(records: Sequence[Record], tx: Tx | None = None) -> None:
        seen.append(tx)
        await save(records, tx)

    service.store.save_records = recording_save  # type: ignore[method-assign]
    put_record(client, ITEM_ID, ITEM)
    assert seen == [SESSION]
