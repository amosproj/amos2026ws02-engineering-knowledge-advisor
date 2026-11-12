import pytest
from fakes import make_service

from services import JsonObject
from services.cad.model import BoundingBox, CadDefinition, CadModel, CadOccurrence
from services.cad.to_records import CadRecords, to_records
from services.ograg.service import OgRagService, ParentLimitError

MACHINE_ID = "machine"
UNIT_BOX = BoundingBox((0, 0, 0), (0.01, 0.01, 0.01))


def frame_model() -> CadModel:
    """A frame holding a screw twice and an unnamed plate."""
    return CadModel(
        source_name="frame.step",
        definitions={
            "0:1:1:1": CadDefinition(
                "0:1:1:1", "Frame", BoundingBox((0, 0, 0), (0.11, 0.01, 0.02))
            ),
            "0:1:1:2": CadDefinition("0:1:1:2", "Screw", UNIT_BOX),
            "0:1:1:3": CadDefinition("0:1:1:3", "", None),
        },
        occurrences=[
            CadOccurrence("0:1:1:1", "0:1:1:1", None, "Frame", None),
            CadOccurrence("0:1:1:1/0:1:1:1:1", "0:1:1:2", "0:1:1:1", "Screw", "S:1"),
            CadOccurrence("0:1:1:1/0:1:1:1:2", "0:1:1:2", "0:1:1:1", "Screw", "S:2"),
            CadOccurrence("0:1:1:1/0:1:1:1:3", "0:1:1:3", "0:1:1:1", "Plate", None),
        ],
        bounding_box=BoundingBox((0.1, 0, 0), (0.21, 0.01, 0.02)),
    )


def of_type(records: CadRecords, cls: str) -> dict[str, JsonObject]:
    return {
        record_id: node
        for record_id, node in records.nodes.items()
        if node["@type"] == cls
    }


def by_name(nodes: dict[str, JsonObject], name: str) -> list[str]:
    return [record_id for record_id, node in nodes.items() if node["name"] == name]


def test_one_group_per_definition_shared_by_its_instances():
    records: CadRecords = to_records(frame_model(), MACHINE_ID)

    groups: dict[str, JsonObject] = of_type(records, "AssemblyGroup")
    instances: dict[str, JsonObject] = of_type(records, "AssemblyInstance")
    assert len(groups) == 3 and len(instances) == 4
    (screw_group,) = by_name(groups, "Screw")
    assert groups[screw_group] == {
        "@type": "AssemblyGroup",
        "identifier": "Screw",
        "name": "Screw",
        "definedIn": MACHINE_ID,
        "properties": {"sizeX": 0.01, "sizeY": 0.01, "sizeZ": 0.01},
    }
    screws: list[str] = by_name(instances, "S:1") + by_name(instances, "S:2")
    assert [instances[screw]["instanceOf"] for screw in screws] == [screw_group] * 2


def test_instances_form_the_tree_under_the_machine():
    records: CadRecords = to_records(frame_model(), MACHINE_ID)

    instances: dict[str, JsonObject] = of_type(records, "AssemblyInstance")
    (root,) = by_name(instances, "Frame")
    assert instances[root]["rootOf"] == MACHINE_ID
    assert "partOf" not in instances[root]
    (screw,) = by_name(instances, "S:2")
    assert instances[screw]["partOf"] == root
    assert "rootOf" not in instances[screw]
    assert instances[screw]["properties"] == {
        "occurrenceId": "0:1:1:1/0:1:1:1:2",
        "path": "Frame/S:2",
    }
    assert list(records.nodes).index(root) < list(records.nodes).index(screw)


def test_unnamed_definition_takes_its_occurrence_name_and_may_have_no_size():
    records: CadRecords = to_records(frame_model(), MACHINE_ID)

    groups: dict[str, JsonObject] = of_type(records, "AssemblyGroup")
    (plate,) = by_name(groups, "Plate")
    assert groups[plate]["identifier"] == "Plate"
    assert "properties" not in groups[plate]


def test_machine_size_comes_from_the_model_box():
    model: CadModel = frame_model()
    assert to_records(model, MACHINE_ID).machine_properties == {
        "sizeX": 0.11,
        "sizeY": 0.01,
        "sizeZ": 0.02,
    }
    model.bounding_box = None
    assert to_records(model, MACHINE_ID).machine_properties == {}


async def save(service: OgRagService, records: CadRecords) -> None:
    await service.upsert_record(MACHINE_ID, {"@type": "Machine", "name": "RC-01"})
    for record_id, node in records.nodes.items():
        assert await service.upsert_record(record_id, node) == []


@pytest.mark.anyio
async def test_records_are_valid_for_the_ontology():
    await save(make_service(), to_records(frame_model(), MACHINE_ID))


@pytest.mark.anyio
async def test_several_roots_are_refused_by_the_store():
    model: CadModel = frame_model()
    model.occurrences.append(CadOccurrence("0:1:1:2", "0:1:1:2", None, "Screw", None))
    with pytest.raises(ParentLimitError):
        await save(make_service(), to_records(model, MACHINE_ID))
