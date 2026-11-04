from typing import Any

import pytest
from fakes import load_document, load_ontology

from services import Json, Lane
from services.ograg.ontology import Ontology, Property, get_local_name

GROUP_ID: str = "AG-1"
ITEM_ID: str = "KI-1"
MACHINE_NAME: str = "Robot cell"


@pytest.mark.parametrize(
    ("iri", "name"),
    [
        ("og:Machine", "Machine"),
        ("https://example.org/ograg/ontology#appliesTo", "appliesTo"),
        ("Text", "Text"),
    ],
)
def test_local_name(iri: str, name: str):
    assert get_local_name(iri) == name


def test_property_is_frozen():
    prop = Property("name", "Machine", "Text")
    with pytest.raises(AttributeError):
        prop.name = "other"  # type: ignore[misc]


def test_an_ordinary_link_to_the_own_class_is_allowed():
    onto: Ontology = load_ontology()
    relates_to: Property = onto.properties[("KnowledgeItem", "relatesTo")]
    assert onto.is_link(relates_to) and not relates_to.is_parent_link


def test_nested_properties_are_neither_links_nor_literals():
    onto: Ontology = load_ontology()
    assert onto.is_nested(onto.properties[("AssemblyGroup", "hasCharacteristic")])
    assert not onto.is_nested(onto.properties[("AssemblyGroup", "partOf")])
    assert not onto.is_nested(onto.properties[("AssemblyGroup", "name")])


def test_lane_by_guideline_when():
    onto: Ontology = load_ontology()
    item: dict[str, Any] = {
        "@type": "KnowledgeItem",
        "@id": ITEM_ID,
        "itemType": "consideration",
        "statement": "Keep it simple.",
    }
    group: dict[str, Any] = {
        "@type": "AssemblyGroup",
        "@id": GROUP_ID,
        "name": "Input tray",
    }
    assert onto.get_lane({**item, "scope": "global"}) is Lane.GUIDELINE
    assert onto.get_lane({**item, "scope": "machine-specific"}) is Lane.FACT
    assert (
        onto.get_lane({**item, "scope": "global", "itemType": "lesson learned"})
        is Lane.FACT
    )
    assert onto.get_lane(group) is Lane.FACT
    assert Lane.FACT == "fact"  # members are plain strings


@pytest.mark.parametrize(
    ("voltage", "lane"),
    [
        (24, Lane.GUIDELINE),
        ("24", Lane.GUIDELINE),
        (24.0, Lane.GUIDELINE),
        (48, Lane.FACT),
    ],
)
def test_a_condition_on_a_number_property_compares_numbers(voltage: Json, lane: Lane):
    document: dict[str, Any] = load_document()
    voltage_prop: dict[str, Any] = {
        "@id": "og:ratedVoltage",
        "@type": "rdf:Property",
        "domain": "og:Machine",
        "range": "schema:Number",
    }
    document["@graph"].append(voltage_prop)
    for item in document["@graph"]:
        if item["@id"] == "og:Machine":
            item["og:guidelineWhen"] = {"ratedVoltage": ["24"]}
    onto: Ontology = Ontology.from_jsonld(document)
    graph, warnings = onto.validate_node(
        {"@type": "Machine", "name": MACHINE_NAME, "ratedVoltage": voltage}
    )
    assert warnings == []
    assert onto.get_lane(graph) is lane
