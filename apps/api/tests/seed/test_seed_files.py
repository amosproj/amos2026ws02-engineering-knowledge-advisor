import json
from pathlib import Path
from typing import Any

import pytest
from fakes import load_document

SEED_FILE: Path = (
    Path(__file__).parents[2] / "seed" / "bosch-example" / "knowledge-items.json"
)


def _seed() -> dict[str, Any]:
    return json.loads(SEED_FILE.read_text("utf-8"))


def _property(graph: list[dict[str, Any]], name: str, domain: str) -> dict[str, Any]:
    for item in graph:
        domains = item.get("domain")
        if item["@id"] == f"og:{name}" and (
            domains == domain or (isinstance(domains, list) and domain in domains)
        ):
            return item
    raise AssertionError(f"og:{name} on {domain} not in the ontology")


def _knowledge_property_names(graph: list[dict[str, Any]]) -> set[str]:
    return {
        item["@id"].removeprefix("og:")
        for item in graph
        if item.get("domain") == "og:KnowledgeProperties"
    }


ITEMS: list[dict[str, Any]] = _seed()["items"]


def test_seed_set_size_and_unique_ids():
    assert 15 <= len(ITEMS) <= 20
    ids: list[str] = [item["id"] for item in ITEMS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("item", ITEMS, ids=lambda item: item["id"])
def test_seed_item_matches_ontology(item: dict[str, Any]):
    graph: list[dict[str, Any]] = load_document()["@graph"]
    item_types: list[str] = _property(graph, "itemType", "og:KnowledgeItem")["enum"]
    confidences: list[str] = _property(graph, "confidence", "og:KnowledgeProperties")[
        "enum"
    ]

    assert item["itemType"] in item_types
    assert item["author"].strip()
    assert bool(item.get("appliesTo")) != bool(item.get("appliesToMachine"))
    assert item["source"]["id"] in _seed()["sources"]

    properties: dict[str, str] = item["properties"]
    assert set(properties) <= _knowledge_property_names(graph)
    assert properties["name"].strip() and properties["statement"].strip()
    assert properties["confidence"] in confidences
