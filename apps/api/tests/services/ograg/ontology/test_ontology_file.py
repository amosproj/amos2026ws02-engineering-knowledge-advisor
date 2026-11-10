import json
from pathlib import Path
from typing import Any

import pytest
from fakes import build_ontology_with, load_document, load_ontology
from helpers import assert_mentions

from services import Json, SearchMode
from services.ograg.ontology import Ontology, OntologyError, Property

# text property added to Machine, tests set its og:search
NOTE: dict[str, Any] = {
    "@id": "og:note",
    "@type": "rdf:Property",
    "domain": "og:Machine",
    "range": "schema:Text",
}


def test_record_classes_and_anchor_are_read():
    onto: Ontology = load_ontology()
    assert onto.record_classes == [
        "Machine",
        "AssemblyGroup",
        "CadFile",
        "KnowledgeItem",
        "Guideline",
    ]
    assert onto.anchor_class == "AssemblyGroup"
    assert onto.extractable_classes == ["KnowledgeItem", "Guideline"]
    assert onto.guideline_classes == ["Guideline"]
    assert onto.properties[("AssemblyGroup", "name")].identity
    assert onto.properties[("KnowledgeItem", "appliesTo")].is_parent_link
    assert onto.properties[("CadFile", "partOf")].is_parent_link
    assert onto.properties[("Guideline", "sourceDocumentId")].provenance
    assert onto.get_identity_property_names() == {
        "Machine": ["identifier", "name"],
        "AssemblyGroup": ["identifier", "name"],
        "CadFile": [],
        "KnowledgeItem": [],
        "Guideline": [],
    }


def test_file_classes_and_delete_with_parent_are_read():
    onto: Ontology = load_ontology()
    assert onto.file_classes == ["CadFile"]
    # a parent link to the own class: groups inside groups
    assert onto.properties[("AssemblyGroup", "partOf")].range == "AssemblyGroup"
    assert onto.properties[("AssemblyGroup", "partOf")].delete_with_parent
    assert onto.properties[("AssemblyGroup", "rootOf")].delete_with_parent
    assert onto.properties[("CadFile", "partOf")].delete_with_parent
    assert not onto.properties[("KnowledgeItem", "appliesTo")].delete_with_parent
    assert not onto.properties[("KnowledgeItem", "appliesToMachine")].delete_with_parent


def test_a_machine_has_one_cad_file():
    onto: Ontology = load_ontology()
    assert onto.properties[("CadFile", "partOf")].max_per_parent == 1
    assert onto.properties[("AssemblyGroup", "partOf")].max_per_parent is None


@pytest.mark.parametrize("limit", [0, -1, 1.5, "1", True])
def test_max_per_parent_must_be_a_positive_integer(limit: Json):
    document: dict[str, Any] = load_document()
    for item in document["@graph"]:
        if item["@id"] == "og:partOf" and item["domain"] == "og:CadFile":
            item["og:maxPerParent"] = limit
    with pytest.raises(OntologyError) as raised:
        Ontology.from_jsonld(document)
    assert_mentions(str(raised.value), "CadFile", "partOf", "maxPerParent")


@pytest.mark.parametrize(
    ("file_class_ids", "expected"),
    [
        ([], {"Machine"}),
        # appliesTo and appliesToMachine are parent links
        (["og:KnowledgeItem"], {"Machine", "AssemblyGroup"}),
    ],
    ids=["CAD files", "knowledge items carry files too"],
)
def test_file_parent_classes_follow_the_parent_links_of_file_classes(
    file_class_ids: list[str], expected: set[str]
):
    document: dict[str, Any] = load_document()
    for item in document["@graph"]:
        if item["@id"] in file_class_ids:
            item["og:file"] = True
    assert Ontology.from_jsonld(document).get_file_parent_classes() == expected


def test_labels_are_read():
    onto: Ontology = load_ontology()
    assert onto.class_labels["CadFile"].display_name == "CAD file"
    assert onto.class_labels["CadFile"].comment
    assert onto.properties[("AssemblyProperties", "dimensions")].display_name == (
        "dimensions"
    )
    assert onto.properties[("AssemblyProperties", "dimensions")].comment


@pytest.mark.parametrize(
    "annotations",
    [{}, {"range": "og:KnowledgeItem"}],
    ids=["text property", "ordinary link"],
)
def test_delete_with_parent_on_a_property_without_parent_link_is_refused(
    annotations: dict[str, Any],
):
    prop: dict[str, Any] = {**NOTE, "og:deleteWithParent": True, **annotations}
    with pytest.raises(OntologyError) as raised:
        build_ontology_with(prop)
    assert_mentions(str(raised.value), "deleteWithParent", "Machine", "note")


@pytest.mark.parametrize(
    "annotations",
    [{}, {"range": "og:KnowledgeItem"}],
    ids=["text property", "ordinary link"],
)
def test_max_per_parent_on_a_property_without_parent_link_is_refused(
    annotations: dict[str, Any],
):
    prop: dict[str, Any] = {**NOTE, "og:maxPerParent": 1, **annotations}
    with pytest.raises(OntologyError) as raised:
        build_ontology_with(prop)
    assert_mentions(str(raised.value), "maxPerParent", "Machine", "note")


def test_function_tag_values_have_rules():
    onto: Ontology = load_ontology()
    payload: Property = onto.properties[("FunctionTag", "payloadKg")]
    smallest: Property = onto.properties[("FunctionTag", "workpieceSizeMinMm")]
    assert (payload.min_value, payload.upper_bound) == (0, None)
    assert (smallest.min_value, smallest.upper_bound) == (0, "workpieceSizeMaxMm")
    assert [
        name
        for (domain, name), prop in onto.properties.items()
        if domain == "FunctionTag" and prop.reject_invalid
    ] == ["loadingMode", "payloadKg", "workpieceSizeMinMm", "workpieceSizeMaxMm"]


def test_reject_invalid_on_a_nested_property_is_refused():
    with pytest.raises(OntologyError) as raised:
        build_ontology_with(
            {
                "@id": "og:extra",
                "@type": "rdf:Property",
                "domain": "og:Machine",
                "range": "og:MachineProperties",
                "og:rejectInvalid": True,
            }
        )
    assert_mentions(str(raised.value), "rejectInvalid", "Machine", "extra")


@pytest.mark.parametrize("min_value", ["0", True, float("inf")])
def test_min_value_must_be_a_finite_number(min_value: Json):
    number: dict[str, Any] = {**NOTE, "range": "schema:Number"}
    with pytest.raises(OntologyError) as raised:
        build_ontology_with({**number, "og:minValue": min_value})
    assert_mentions(str(raised.value), "minValue", "Machine", "note")


def test_min_value_on_a_text_property_is_refused():
    with pytest.raises(OntologyError) as raised:
        build_ontology_with({**NOTE, "og:minValue": 0})
    assert_mentions(str(raised.value), "minValue", "Machine", "note")


@pytest.mark.parametrize(
    "upper_bound",
    ["og:name", "og:missing", "og:note", 3],
    ids=["text property", "unknown property", "itself", "no name"],
)
def test_upper_bound_must_name_another_number_property(upper_bound: Json):
    number: dict[str, Any] = {**NOTE, "range": "schema:Number"}
    with pytest.raises(OntologyError) as raised:
        build_ontology_with({**number, "og:upperBound": upper_bound})
    assert_mentions(str(raised.value), "upperBound", "Machine", "note")


def test_file_on_a_class_that_is_no_record_class_is_refused():
    document: dict[str, Any] = load_document()
    for item in document["@graph"]:
        if item["@id"] == "og:AssemblyProperties":
            item["og:file"] = True
    with pytest.raises(OntologyError) as raised:
        Ontology.from_jsonld(document)
    assert_mentions(str(raised.value), "AssemblyProperties", "record")


@pytest.mark.parametrize(
    ("class_id", "annotations", "keywords"),
    [
        ("og:AssemblyProperties", {}, ("AssemblyProperties", "guideline", "record")),
        ("og:AssemblyGroup", {}, ("AssemblyGroup", "guideline", "anchor")),
        (
            "og:KnowledgeItem",
            {"og:guidelineWhen": {"itemType": ["requirement"]}},
            ("KnowledgeItem", "guideline", "guidelineWhen"),
        ),
    ],
    ids=["no record class", "anchor", "next to guidelineWhen"],
)
def test_a_misplaced_guideline_flag_is_refused(
    class_id: str, annotations: dict[str, Any], keywords: tuple[str, ...]
):
    document: dict[str, Any] = load_document()
    for item in document["@graph"]:
        if item["@id"] == class_id:
            item.update({"og:guideline": True, **annotations})
    with pytest.raises(OntologyError) as raised:
        Ontology.from_jsonld(document)
    assert_mentions(str(raised.value), *keywords)


def test_a_property_listing_several_domains_is_added_to_each():
    onto: Ontology = build_ontology_with(
        {**NOTE, "domain": ["og:Machine", "og:CadFile"], "og:search": ["lexical"]}
    )
    for cls in ("Machine", "CadFile"):
        assert onto.properties[(cls, "note")].search == (SearchMode.LEXICAL,)
    # the file's shared name: one comment for both classes, CadFile keeps its own item
    machine_name, group_name = (
        onto.properties[(cls, "name")] for cls in ("Machine", "AssemblyGroup")
    )
    assert machine_name.identity and machine_name.comment == group_name.comment
    assert not onto.properties[("CadFile", "name")].identity


@pytest.mark.parametrize(
    ("domain", "keywords"),
    [
        (["og:Machine", "og:Machine"], ("Machine", "note", "twice")),
        ("og:AssemblyGroup", ("AssemblyGroup", "name", "twice")),
        ([], ("note", "domain")),
        (["og:Machine", 3], ("note", "domain")),
        (3, ("note", "domain")),
    ],
    ids=["listed twice", "defined again", "empty list", "not a text", "number"],
)
def test_a_property_defined_twice_or_with_a_bad_domain_is_refused(
    domain: Json, keywords: tuple[str, ...]
):
    name: str = "og:name" if "name" in keywords else "og:note"
    with pytest.raises(OntologyError) as raised:
        build_ontology_with({**NOTE, "@id": name, "domain": domain})
    assert_mentions(str(raised.value), *keywords)


@pytest.mark.parametrize(
    ("annotations", "keywords"),
    [
        ({"displayName": 3}, ("note", "displayName")),
        ({"comment": ["a", "b"]}, ("note", "comment")),
    ],
)
def test_labels_of_the_wrong_shape_are_refused(
    annotations: dict[str, Any], keywords: tuple[str, ...]
):
    with pytest.raises(OntologyError) as raised:
        build_ontology_with({**NOTE, **annotations})
    assert_mentions(str(raised.value), *keywords)


def test_search_modes_default_by_range():
    onto: Ontology = build_ontology_with({**NOTE, "og:search": []})
    assert onto.properties[("KnowledgeProperties", "statement")].search == ("semantic",)
    assert onto.properties[("AssemblyProperties", "dimensions")].search == ("filter",)
    assert onto.properties[("AssemblyGroup", "partOf")].search == ()
    assert onto.properties[("Machine", "note")].search == ()
    assert "lexical" in (onto.properties[("AssemblyGroup", "identifier")].search or ())


def test_search_modes_are_enum_members():
    onto: Ontology = load_ontology()
    identifier: tuple[SearchMode, ...] = (
        onto.properties[("AssemblyGroup", "identifier")].search or ()
    )
    assert identifier == (SearchMode.SEMANTIC, SearchMode.LEXICAL)
    assert all(isinstance(mode, SearchMode) for mode in identifier)


def test_an_unknown_search_mode_is_refused():
    typo: dict[str, Any] = {**NOTE, "og:search": ["semantics"]}
    with pytest.raises(OntologyError) as raised:
        build_ontology_with(typo)
    assert_mentions(str(raised.value), "Machine", "note", "semantics")


def test_malformed_ontology_is_refused():
    second_anchor: dict[str, Any] = {
        "@id": "og:Cell",
        "@type": "rdfs:Class",
        "og:record": True,
        "og:anchor": True,
    }
    with pytest.raises(OntologyError, match="anchor"):
        build_ontology_with(second_anchor)

    document: dict[str, Any] = load_document()
    for item in document["@graph"]:
        if item["@id"] == "og:AssemblyGroup":
            del item["og:record"]
    with pytest.raises(OntologyError, match="record"):
        Ontology.from_jsonld(document)

    unknown_range: dict[str, Any] = {
        "@id": "og:mystery",
        "@type": "rdf:Property",
        "domain": "og:Machine",
        "range": "og:Nowhere",
    }
    with pytest.raises(OntologyError) as raised_range:
        build_ontology_with(unknown_range)
    assert_mentions(str(raised_range.value), "mystery", "range")

    unknown_domain: dict[str, Any] = {
        **unknown_range,
        "domain": "og:Nowhere",
        "range": "schema:Text",
    }
    with pytest.raises(OntologyError) as raised_domain:
        build_ontology_with(unknown_domain)
    assert_mentions(str(raised_domain.value), "mystery", "domain")


@pytest.mark.parametrize(
    ("domain", "range_", "keywords"),
    [
        ("og:Machine", "og:AssemblyGroup", ("Machine", "AssemblyGroup")),
        ("og:Machine", "og:CadFile", ("Machine", "CadFile")),
    ],
    ids=["through another class", "two classes"],
)
def test_parent_links_leading_back_to_their_class_through_others_are_refused(
    domain: str, range_: str, keywords: tuple[str, ...]
):
    parent_link: dict[str, Any] = {
        "@id": "og:inside",
        "@type": "rdf:Property",
        "domain": domain,
        "range": range_,
        "og:edgeType": "parent",
    }
    with pytest.raises(OntologyError) as raised:
        build_ontology_with(parent_link)
    assert_mentions(str(raised.value), "parent", *keywords)


@pytest.mark.parametrize(
    ("annotations", "keywords"),
    [
        ({"og:edgeType": "child"}, ("Machine", "note", "edgeType", "child")),
        ({"og:edgeType": ["parent"]}, ("Machine", "note", "edgeType")),
        (
            {"range": "schema:Text", "og:edgeType": "simple"},
            ("Machine", "note", "edgeType", "link"),
        ),
        ({"og:parentLink": True}, ("Machine", "note", "parentLink", "edgeType")),
    ],
    ids=["unknown", "not a text", "on a text property", "old parentLink"],
)
def test_a_bad_edge_type_is_refused(
    annotations: dict[str, Any], keywords: tuple[str, ...]
):
    link: dict[str, Any] = {**NOTE, "range": "og:KnowledgeItem", **annotations}
    with pytest.raises(OntologyError) as raised:
        build_ontology_with(link)
    assert_mentions(str(raised.value), *keywords)


def test_a_link_without_edge_type_is_simple():
    onto: Ontology = build_ontology_with({**NOTE, "range": "og:KnowledgeItem"})
    note: Property = onto.properties[("Machine", "note")]
    assert note.edge is None and not note.is_parent_link
    assert onto.describe()["Machine"].properties["note"].edge == "simple"


@pytest.mark.parametrize(
    ("missing", "keywords"),
    [
        ("domain", ("mystery", "domain")),
        ("range", ("mystery", "range")),
        ("@id", ("@id",)),
        ("@type", ("@type", "mystery")),
    ],
)
def test_an_item_without_a_required_key_is_refused(
    missing: str, keywords: tuple[str, ...]
):
    item: dict[str, Any] = {
        "@id": "og:mystery",
        "@type": "rdf:Property",
        "domain": "og:Machine",
        "range": "schema:Text",
    }
    del item[missing]
    with pytest.raises(OntologyError) as raised:
        build_ontology_with(item)
    assert_mentions(str(raised.value), *keywords)


def test_guideline_when_naming_properties_its_class_lacks_is_refused():
    document: dict[str, Any] = load_document()
    for item in document["@graph"]:
        if item["@id"] == "og:KnowledgeItem":
            item["og:guidelineWhen"] = {
                "itemType": ["requirement"],
                "scop": ["global"],
                "dimensions": ["12"],
            }
    with pytest.raises(OntologyError) as raised:
        Ontology.from_jsonld(document)
    assert_mentions(str(raised.value), "KnowledgeItem", "scop", "dimensions")


@pytest.mark.parametrize(
    ("conditions", "keywords"),
    [
        (["global"], ("KnowledgeItem", "guidelineWhen")),
        ({"scope": "global"}, ("KnowledgeItem", "scope", "global")),
        ({"scope": [1]}, ("KnowledgeItem", "scope")),
    ],
)
def test_guideline_when_of_the_wrong_shape_is_refused(
    conditions: Json, keywords: tuple[str, ...]
):
    document: dict[str, Any] = load_document()
    for item in document["@graph"]:
        if item["@id"] == "og:KnowledgeItem":
            item["og:guidelineWhen"] = conditions
    with pytest.raises(OntologyError) as raised:
        Ontology.from_jsonld(document)
    assert_mentions(str(raised.value), *keywords)


@pytest.mark.parametrize(
    ("annotations", "keywords"),
    [
        ({"og:search": "semantic"}, ("Machine", "note", "search")),
        ({"og:search": ["semantic", 2]}, ("Machine", "note", "search")),
        ({"enum": "global"}, ("Machine", "note", "enum")),
        ({"og:allowedValues": {"a": 1}}, ("Machine", "note", "allowedValues")),
    ],
)
def test_property_annotations_of_the_wrong_shape_are_refused(
    annotations: dict[str, Any], keywords: tuple[str, ...]
):
    with pytest.raises(OntologyError) as raised:
        build_ontology_with({**NOTE, **annotations})
    assert_mentions(str(raised.value), *keywords)


def test_graph_must_be_a_list_of_objects():
    document: dict[str, Any] = load_document()
    document["@graph"].append("og:Machine")
    with pytest.raises(OntologyError, match="@graph"):
        Ontology.from_jsonld(document)

    with pytest.raises(OntologyError, match="@graph"):
        Ontology.from_jsonld({"@graph": {"@id": "og:Machine"}})


def test_a_file_without_a_json_object_is_refused(tmp_path: Path):
    path: Path = tmp_path / "ontology.jsonld"
    path.write_text(json.dumps([load_document()]), "utf-8")
    with pytest.raises(OntologyError):
        Ontology.load(path)
