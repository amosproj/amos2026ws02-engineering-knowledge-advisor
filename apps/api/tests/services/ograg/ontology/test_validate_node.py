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


def group_with_tag(tag: dict[str, Json]) -> dict[str, Json]:
    return {
        "@type": "AssemblyGroup",
        "name": GROUP_NAME,
        "properties": {"functionTag": tag},
    }


def validate_function_tag(tag: dict[str, Json]) -> tuple[dict[str, Any], list[str]]:
    return load_ontology().validate_node(group_with_tag(tag))


def find_function_tag_violation(tag: dict[str, Json]) -> str | None:
    graph, _ = validate_function_tag(tag)
    return load_ontology().find_rule_violation(graph, group_with_tag(tag))


def test_a_function_tag_keeps_its_values_and_leaves_unknown_ones_unset():
    graph, warnings = validate_function_tag(
        {"function": "gripper", "loadingMode": "Robot", "payloadKg": None}
    )
    assert warnings == []
    assert graph["properties"]["functionTag"] == {
        "@type": "FunctionTag",
        "function": "gripper",
        "loadingMode": "robot",
    }


@pytest.mark.parametrize(
    "sizes",
    [
        {"workpieceSizeMinMm": 0, "workpieceSizeMaxMm": 0},
        {"workpieceSizeMinMm": 20, "workpieceSizeMaxMm": "20"},
        {"workpieceSizeMinMm": 20},
        {"workpieceSizeMaxMm": 0.5},
    ],
    ids=["zero", "equal", "only min", "only max"],
)
def test_a_workpiece_size_range_may_be_open_or_a_single_size(sizes: dict[str, Json]):
    graph, warnings = validate_function_tag({"payloadKg": 0, **sizes})
    assert warnings == []
    assert graph["properties"]["functionTag"]["payloadKg"] == 0
    assert find_function_tag_violation({"payloadKg": 0, **sizes}) is None


@pytest.mark.parametrize(
    ("tag", "words"),
    [
        ({"payloadKg": -0.1}, ["payloadKg", "at least 0", "-0.1"]),
        ({"workpieceSizeMinMm": "-5"}, ["workpieceSizeMinMm", "at least 0", "-5"]),
        ({"workpieceSizeMaxMm": -1}, ["workpieceSizeMaxMm", "at least 0", "-1"]),
        (
            {"workpieceSizeMinMm": 50, "workpieceSizeMaxMm": 20},
            ["workpieceSizeMinMm", "greater than", "workpieceSizeMaxMm", "50", "20"],
        ),
    ],
    ids=["negative payload", "negative min", "negative max", "min above max"],
)
def test_a_broken_rule_is_kept_by_the_cleaning_and_found_by_the_rule_check(
    tag: dict[str, Json], words: list[str]
):
    # cleaning keeps the values: a stored record must stay readable after a rule changes
    graph, warnings = validate_function_tag(tag)
    assert warnings == []
    assert graph["properties"]["functionTag"]["@type"] == "FunctionTag"

    violation: str | None = find_function_tag_violation(tag)
    assert violation is not None
    assert_mentions(violation, *words)


@pytest.mark.parametrize(
    ("tag", "words"),
    [
        ({"loadingMode": "forklift"}, ["loadingMode", "forklift", "not one of"]),
        ({"payloadKg": "12 kg"}, ["payloadKg", "12 kg", "not a number"]),
        ({"workpieceSizeMinMm": "nan"}, ["workpieceSizeMinMm", "nan", "not a number"]),
        ({"loadingMode": {"mode": "robot"}}, ["loadingMode", "not a single value"]),
    ],
    ids=["unknown loading mode", "payload with unit", "size not a number", "object"],
)
def test_an_invalid_function_tag_value_is_rejected_instead_of_dropped(
    tag: dict[str, Json], words: list[str]
):
    violation: str | None = find_function_tag_violation(tag)
    assert violation is not None
    assert_mentions(violation, *words)


def test_other_invalid_values_are_still_dropped_with_a_warning():
    # itemType has no og:rejectInvalid: extracted records keep their valid values
    node: dict[str, Json] = {
        "@type": "KnowledgeItem",
        "itemType": "requirment",
        "properties": {"statement": "x"},
    }
    graph, warnings = load_ontology().validate_node(node)
    assert len(warnings) == 1
    assert load_ontology().find_rule_violation(graph, node) is None
