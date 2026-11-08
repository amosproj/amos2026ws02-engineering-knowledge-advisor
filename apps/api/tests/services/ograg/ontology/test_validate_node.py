from typing import Any

import pytest
from fakes import load_ontology
from helpers import assert_mentions

from services import Json, Link
from services.ograg.ontology import Ontology

GROUP_ID: str = "AG-1"
OTHER_GROUP_ID: str = "AG-2"
ITEM_ID: str = "KI-1"
MACHINE_NAME: str = "Robot cell"
GROUP_NAME: str = "Gripper"
UNSTORABLE_NAME: str = "nul \x00 byte"


def validate_payload(payload: Json) -> tuple[dict[str, Any], list[str]]:
    return load_ontology().validate_node(
        {
            "@type": "AssemblyGroup",
            "name": GROUP_NAME,
            "properties": {"dimensions": payload},
        }
    )


def test_links_are_kept_as_ids():
    onto: Ontology = load_ontology()
    graph, warnings = onto.validate_node(
        {
            "@type": "KnowledgeItem",
            "@id": ITEM_ID,
            "properties": {"statement": "Chamfer the nest."},
            "appliesTo": [GROUP_ID, {"@id": OTHER_GROUP_ID}],
        },
        "KnowledgeItem",
    )
    assert warnings == []
    assert graph["appliesTo"] == [GROUP_ID, OTHER_GROUP_ID]
    assert onto.is_link(onto.properties[("KnowledgeItem", "appliesTo")])
    # A nested node, not a record:
    assert not onto.is_link(onto.properties[("AssemblyGroup", "properties")])
    expected: list[Link] = [
        Link("appliesTo", GROUP_ID),
        Link("appliesTo", OTHER_GROUP_ID),
    ]
    assert onto.get_links(graph) == expected


def test_prefixed_types_and_keys_are_accepted():
    graph, warnings = load_ontology().validate_node(
        {"@type": "og:Machine", "og:name": MACHINE_NAME}
    )
    assert (graph, warnings) == ({"@type": "Machine", "name": MACHINE_NAME}, [])


def test_unknown_properties_and_types_are_dropped_with_a_warning():
    onto: Ontology = load_ontology()
    graph, warnings = onto.validate_node(
        {"@type": "AssemblyGroup", "name": GROUP_NAME, "colour": "red"}
    )
    assert graph == {"@type": "AssemblyGroup", "name": GROUP_NAME}
    assert len(warnings) == 1
    assert_mentions(warnings[0], "AssemblyGroup", "colour")

    unknown_graph, unknown_warnings = onto.validate_node(
        {"@type": "Spaceship", "name": "x"}
    )
    assert unknown_graph == {} and len(unknown_warnings) == 1
    assert_mentions(unknown_warnings[0], "Spaceship")


def test_allowed_values_are_matched_ignoring_case_and_others_dropped():
    graph, warnings = load_ontology().validate_node(
        {
            "@type": "KnowledgeItem",
            "itemType": "requirment",
            "properties": {"confidence": "Rule of Thumb", "statement": "x"},
        }
    )
    # the ontology's spelling, also in a nested node
    nested: Json = graph["properties"]
    assert isinstance(nested, dict) and nested["confidence"] == "rule of thumb"
    assert "itemType" not in graph
    assert len(warnings) == 1
    assert_mentions(warnings[0], "itemType", "requirment")


@pytest.mark.parametrize(
    ("payload", "stored"),
    [(12, 12), ("12", 12), (12.5, 12.5), ("0.5", 0.5), (-3, -3), ("1e3", 1000.0)],
)
def test_numbers_are_stored_as_numbers(payload: Json, stored: float):
    graph, warnings = validate_payload(payload)
    assert warnings == []
    kept: Json = graph["properties"]["dimensions"]
    assert kept == stored and type(kept) is type(stored)


def test_text_that_looks_like_a_number_stays_text():
    graph, _ = load_ontology().validate_node({"@type": "Machine", "name": "12"})
    assert graph["name"] == "12"


@pytest.mark.parametrize("payload", ["12 kg", "12,5", "nan", "inf", True])
def test_a_number_property_drops_what_is_no_number(payload: Json):
    graph, warnings = validate_payload(payload)
    assert "properties" not in graph  # nothing else was left in it
    assert len(warnings) == 1
    assert_mentions(warnings[0], "dimensions", str(payload))


def test_text_is_kept_as_given_the_store_decides_what_it_can_store():
    graph, warnings = load_ontology().validate_node(
        {"@type": "Machine", "name": UNSTORABLE_NAME}
    )
    assert (graph["name"], warnings) == (UNSTORABLE_NAME, [])
