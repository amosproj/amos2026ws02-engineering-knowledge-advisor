from typing import Any

from fastapi.testclient import TestClient
from httpx2 import Response

ONTOLOGY_URL: str = "/api/v1/ontology"
CLASS_KEYS: set[str] = {
    "displayName",
    "comment",
    "record",
    "anchor",
    "file",
    "guideline",
    "extractable",
    "properties",
}
PROPERTY_KEYS: set[str] = {
    "range",
    "displayName",
    "comment",
    "enum",
    "link",
    "edge",
    "deleteWithParent",
    "nested",
    "identity",
    "search",
}


def test_the_ontology_describes_every_class_with_stable_keys(client: TestClient):
    response: Response = client.get(ONTOLOGY_URL)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["version"]
    classes: dict[str, Any] = body["classes"]
    assert list(classes) == sorted(classes)
    for cls, description in classes.items():
        assert set(description) == CLASS_KEYS, cls
        for prop in description["properties"].values():
            assert set(prop) == PROPERTY_KEYS, cls


def test_the_ontology_tells_files_and_dependents(client: TestClient):
    classes: dict[str, Any] = client.get(ONTOLOGY_URL).json()["classes"]
    cad_file: dict[str, Any] = classes["CadFile"]
    assert cad_file["file"] and cad_file["record"]
    part_of: dict[str, Any] = cad_file["properties"]["partOf"]
    assert (part_of["range"], part_of["edge"], part_of["deleteWithParent"]) == (
        "Machine",
        "parent",
        True,
    )
    assert classes["CadFile"]["properties"]["name"]["edge"] is None
    assert not classes["AssemblyProperties"]["record"]
    assert classes["Guideline"]["guideline"]
