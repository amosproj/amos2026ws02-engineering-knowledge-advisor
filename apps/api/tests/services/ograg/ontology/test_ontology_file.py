import json
from pathlib import Path
from typing import Any

import pytest
from fakes import build_ontology_with, load_document, load_ontology
from helpers import assert_mentions

from services import Json, SearchMode
from services.ograg.ontology import Ontology, OntologyError

# text property added to Machine, tests set its og:search
NOTE: dict[str, Any] = {
    "@id": "og:note",
    "@type": "rdf:Property",
    "domain": "og:Machine",
    "range": "schema:Text",
}


def test_record_classes_and_anchor_are_read():
    onto: Ontology = load_ontology()
    assert onto.record_classes == ["Machine", "AssemblyGroup", "KnowledgeItem"]
    assert onto.anchor_class == "AssemblyGroup"
    assert onto.extractable_classes == ["KnowledgeItem"]
    assert onto.properties[("AssemblyGroup", "name")].identity
    assert onto.properties[("KnowledgeItem", "appliesTo")].is_parent_link
    assert onto.properties[("KnowledgeItem", "author")].author
    assert onto.get_identity_property_names()["AssemblyGroup"] == ["identifier", "name"]


def test_search_modes_default_by_range():
    onto: Ontology = build_ontology_with({**NOTE, "og:search": []})
    assert onto.properties[("KnowledgeItem", "statement")].search == ("semantic",)
    assert onto.properties[("Characteristic", "payloadKg")].search == ("filter",)
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
        ("og:AssemblyGroup", "og:AssemblyGroup", ("AssemblyGroup",)),
        ("og:Machine", "og:AssemblyGroup", ("Machine", "AssemblyGroup")),
    ],
    ids=["own class", "through another class"],
)
def test_parent_links_leading_back_to_their_class_are_refused(
    domain: str, range_: str, keywords: tuple[str, ...]
):
    parent_link: dict[str, Any] = {
        "@id": "og:inside",
        "@type": "rdf:Property",
        "domain": domain,
        "range": range_,
        "og:parentLink": True,
    }
    with pytest.raises(OntologyError) as raised:
        build_ontology_with(parent_link)
    assert_mentions(str(raised.value), "parentLink", *keywords)


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
            item["og:guidelineWhen"] |= {"scop": ["global"], "payloadKg": ["12"]}
    with pytest.raises(OntologyError) as raised:
        Ontology.from_jsonld(document)
    assert_mentions(str(raised.value), "KnowledgeItem", "scop", "payloadKg")


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
