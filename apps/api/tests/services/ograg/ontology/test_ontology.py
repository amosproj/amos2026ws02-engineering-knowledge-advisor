from typing import Any

import pytest
from fakes import build_ontology_with, load_document, load_ontology

from services import Json, Lane, SearchMode
from services.ograg.ontology import (
    ClassDescription,
    EdgeType,
    Ontology,
    Property,
    PropertyDescription,
    get_local_name,
)

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
    onto: Ontology = build_ontology_with(
        {
            "@id": "og:relatesTo",
            "@type": "rdf:Property",
            "domain": "og:KnowledgeItem",
            "range": "og:KnowledgeItem",
        }
    )
    relates_to: Property = onto.properties[("KnowledgeItem", "relatesTo")]
    assert onto.is_link(relates_to) and not relates_to.is_parent_link
    assert onto.describe()["KnowledgeItem"].properties["relatesTo"].edge == "simple"


def test_nested_properties_are_neither_links_nor_literals():
    onto: Ontology = load_ontology()
    assert onto.is_nested(onto.properties[("AssemblyGroup", "properties")])
    assert not onto.is_nested(onto.properties[("AssemblyGroup", "partOf")])
    assert not onto.is_nested(onto.properties[("AssemblyGroup", "name")])


def test_parent_link_names_of_a_class():
    onto: Ontology = load_ontology()
    assert onto.get_parent_link_names("KnowledgeItem") == {
        "appliesTo",
        "appliesToMachine",
    }
    assert onto.get_parent_link_names("CadFile") == {"partOf"}
    assert onto.get_parent_link_names("AssemblyGroup") == {"rootOf", "partOf"}
    assert onto.get_parent_link_names("Machine") == set()


def test_describe_lists_every_class_with_its_properties():
    onto: Ontology = load_ontology()
    described: dict[str, ClassDescription] = onto.describe()
    assert set(described) == onto.classes

    cad_file: ClassDescription = described["CadFile"]
    assert cad_file.record and cad_file.file and not cad_file.anchor
    assert cad_file.display_name == "CAD file"
    part_of: PropertyDescription = cad_file.properties["partOf"]
    assert part_of.range == "Machine"
    assert part_of.link and part_of.edge is EdgeType.PARENT
    assert part_of.delete_with_parent
    assert not part_of.nested
    assert cad_file.properties["timestamp"].range == "DateTime"

    group: ClassDescription = described["AssemblyGroup"]
    assert group.anchor and not group.file and not group.guideline
    assert group.properties["properties"].nested
    assert not group.properties["properties"].link
    assert group.properties["name"].identity
    assert SearchMode.LEXICAL in group.properties["identifier"].search

    group_properties: ClassDescription = described["AssemblyProperties"]
    assert not group_properties.record
    assert group_properties.properties["dimensions"].range == "Number"

    item: ClassDescription = described["KnowledgeItem"]
    assert item.extractable and not item.guideline
    assert not item.properties["appliesTo"].delete_with_parent
    assert described["KnowledgeProperties"].properties["confidence"].enum

    guideline: ClassDescription = described["Guideline"]
    assert guideline.guideline and guideline.extractable and guideline.record


def test_every_record_of_a_guideline_class_takes_the_guideline_lane():
    onto: Ontology = load_ontology()
    guideline: dict[str, Any] = {
        "@type": "Guideline",
        "@id": "GL-1",
        "description": "Above 3 m width, transport becomes very expensive.",
    }
    item: dict[str, Any] = {
        "@type": "KnowledgeItem",
        "@id": ITEM_ID,
        "itemType": "requirement",
    }
    group: dict[str, Any] = {
        "@type": "AssemblyGroup",
        "@id": GROUP_ID,
        "name": "Input tray",
    }
    assert onto.get_lane(guideline) is Lane.GUIDELINE
    assert onto.get_lane(item) is Lane.FACT
    assert onto.get_lane(group) is Lane.FACT
    assert Lane.FACT == "fact"  # members are plain strings


def test_lane_by_guideline_when():
    document: dict[str, Any] = load_document()
    for entry in document["@graph"]:
        if entry["@id"] == "og:KnowledgeItem":
            entry["og:guidelineWhen"] = {"itemType": ["requirement", "consideration"]}
    onto: Ontology = Ontology.from_jsonld(document)
    item: dict[str, Any] = {"@type": "KnowledgeItem", "@id": ITEM_ID}
    assert onto.get_lane({**item, "itemType": "consideration"}) is Lane.GUIDELINE
    assert onto.get_lane({**item, "itemType": "lesson learned"}) is Lane.FACT
    assert onto.get_lane(item) is Lane.FACT


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
