import pytest
from fakes import make_service

from services import Record
from services.catalog.records import (
    ASSEMBLY_GROUP,
    CAD_FILE,
    MACHINE,
    NotFoundError,
    create_assembly_group,
    create_cad_file,
    create_machine,
    delete_machine,
    get_record,
    list_children,
    list_machines,
    update_record,
)
from services.ograg.service import OgRagService, RecordError

pytestmark = pytest.mark.anyio

# the in-memory store ignores transactions
TX = None


async def create_tree(ograg: OgRagService) -> tuple[str, str, str]:
    machine_id: str = await create_machine(
        ograg, TX, {"name": "Robot cell", "identifier": "RC-01"}
    )
    group_id: str = await create_assembly_group(
        ograg, TX, machine_id, {"name": "Input tray", "identifier": "AG-01"}
    )
    cad_file_id: str = await create_cad_file(ograg, TX, group_id, "tray.step")
    return machine_id, group_id, cad_file_id


async def test_records_form_a_tree():
    ograg: OgRagService = make_service()
    machine_id, group_id, cad_file_id = await create_tree(ograg)
    await ograg.upsert_record(
        "KI-1",
        {
            "@type": "KnowledgeItem",
            "statement": "Chamfer the nest.",
            "appliesTo": [group_id],
        },
    )

    assert [rec.id for rec in await list_machines(ograg, TX)] == [machine_id]
    groups: list[Record] = await list_children(ograg, TX, machine_id, ASSEMBLY_GROUP)
    assert [rec.id for rec in groups] == [group_id]
    cad_files: list[Record] = await list_children(ograg, TX, group_id, CAD_FILE)
    assert [rec.id for rec in cad_files] == [cad_file_id]
    assert cad_files[0].graph["format"] == "STEP"


async def test_a_child_needs_an_existing_parent_of_the_right_class():
    ograg: OgRagService = make_service()
    _, group_id, _ = await create_tree(ograg)
    with pytest.raises(NotFoundError):
        await create_assembly_group(ograg, TX, group_id, {"name": "Gripper"})
    with pytest.raises(NotFoundError):
        await create_cad_file(ograg, TX, "ag-missing", "gripper.step")


async def test_an_update_changes_only_the_given_fields():
    ograg: OgRagService = make_service()
    machine_id, group_id, _ = await create_tree(ograg)

    await update_record(
        ograg, TX, ASSEMBLY_GROUP, group_id, {"name": " Tray ", "identifier": ""}
    )

    group: Record = await get_record(ograg, TX, ASSEMBLY_GROUP, group_id)
    assert group.graph["name"] == "Tray"
    assert "identifier" not in group.graph
    assert group.graph["partOf"] == machine_id


async def test_invalid_fields_are_refused():
    ograg: OgRagService = make_service()
    machine_id, _, cad_file_id = await create_tree(ograg)
    with pytest.raises(RecordError):
        await create_machine(ograg, TX, {"name": "  "})
    with pytest.raises(RecordError):
        await update_record(ograg, TX, MACHINE, machine_id, {"name": None})
    with pytest.raises(RecordError):
        await update_record(ograg, TX, CAD_FILE, cad_file_id, {"format": "IGES"})


async def test_identifiers_may_be_shared():
    ograg: OgRagService = make_service()
    machine_id, _, _ = await create_tree(ograg)

    other_id: str = await create_machine(
        ograg, TX, {"name": "Other", "identifier": "RC-01"}
    )
    await create_assembly_group(
        ograg, TX, machine_id, {"name": "x", "identifier": "AG-01"}
    )

    assert await ograg.store.find_record_ids("Machine", "rc-01", TX) == sorted(
        [machine_id, other_id]
    )


async def test_deleting_a_machine_deletes_its_tree_and_keeps_knowledge():
    ograg: OgRagService = make_service()
    machine_id, group_id, cad_file_id = await create_tree(ograg)
    await ograg.upsert_record(
        "KI-1",
        {
            "@type": "KnowledgeItem",
            "statement": "Chamfer the nest.",
            "appliesTo": [group_id],
        },
    )

    deleted_ids: list[str] = await delete_machine(ograg, TX, machine_id)

    assert sorted(deleted_ids) == sorted([machine_id, group_id, cad_file_id])
    item: Record | None = await ograg.store.get_record("KI-1")
    assert item is not None and item.review


async def test_records_written_by_the_generic_endpoint_are_handled():
    ograg: OgRagService = make_service()
    await ograg.upsert_record(
        "M-raw",
        {"@type": "Machine", "og:name": "Raw", "og:identifier": " RC-02 "},
    )

    await update_record(ograg, TX, MACHINE, "M-raw", {"identifier": None})
    raw: Record = await get_record(ograg, TX, MACHINE, "M-raw")
    assert raw.graph["name"] == "Raw"
    assert "identifier" not in raw.graph
