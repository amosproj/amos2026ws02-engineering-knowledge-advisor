from typing import Any

import pytest
from fakes import build_ontology_with, make_catalog, make_service

from services import Link, Record
from services.catalog import CatalogService, TreeNode
from services.catalog.records import (
    NotFoundError,
    create_record,
    delete_tree,
    get_children,
    get_record,
    lock_tree,
    update_record,
)
from services.catalog.service import get_files_status
from services.ograg.service import DeleteResult, OgRagService, RecordError
from services.uploads import UploadStatus

pytestmark = pytest.mark.anyio

# the in-memory store ignores transactions
TX = None
ITEM_ID: str = "KI-1"
# a second parent link of CAD files: to an assembly group
PART_OF_GROUP: dict[str, Any] = {
    "@id": "og:partOfGroup",
    "@type": "rdf:Property",
    "domain": "og:CadFile",
    "range": "og:AssemblyGroup",
    "og:edgeType": "parent",
}


async def create_tree(ograg: OgRagService) -> tuple[str, str, str]:
    machine_id, _ = await create_record(
        ograg, TX, {"@type": "Machine", "name": "Robot cell", "identifier": "RC-01"}
    )
    group_id, _ = await create_record(
        ograg,
        TX,
        {
            "@type": "AssemblyGroup",
            "name": "Input tray",
            "identifier": "AG-01",
            "rootOf": machine_id,
        },
    )
    cad_file_id, _ = await create_record(
        ograg, TX, {"@type": "CadFile", "name": "cell.step", "partOf": machine_id}
    )
    return machine_id, group_id, cad_file_id


async def add_item(ograg: OgRagService, group_id: str) -> None:
    await ograg.upsert_record(
        ITEM_ID,
        {
            "@type": "KnowledgeItem",
            "properties": {"name": "Chamfer", "statement": "Chamfer the nest."},
            "appliesTo": [group_id],
        },
    )


async def test_children_are_the_records_whose_parent_links_point_to_the_parent():
    ograg: OgRagService = make_service()
    machine_id, group_id, cad_file_id = await create_tree(ograg)
    await add_item(ograg, group_id)

    machine_children: list[Record] = await get_children(ograg, TX, [machine_id])
    assert sorted(rec.id for rec in machine_children) == sorted([group_id, cad_file_id])
    group_children: list[Record] = await get_children(ograg, TX, [group_id])
    assert [rec.id for rec in group_children] == [ITEM_ID]
    dependents: list[Record] = await get_children(
        ograg, TX, [group_id], dependents_only=True
    )
    assert dependents == []


async def test_a_record_of_another_class_is_not_found():
    ograg: OgRagService = make_service()
    machine_id, group_id, _ = await create_tree(ograg)
    assert (await get_record(ograg, TX, group_id)).cls == "AssemblyGroup"
    with pytest.raises(NotFoundError):
        await get_record(ograg, TX, machine_id, "AssemblyGroup")
    with pytest.raises(NotFoundError):
        await get_record(ograg, TX, "missing")


async def test_a_child_needs_an_existing_parent_of_the_right_class():
    ograg: OgRagService = make_service()
    _, group_id, _ = await create_tree(ograg)
    with pytest.raises(RecordError):
        await create_record(
            ograg, TX, {"@type": "AssemblyGroup", "name": "x", "rootOf": group_id}
        )
    with pytest.raises(RecordError):
        await create_record(
            ograg, TX, {"@type": "CadFile", "name": "x.step", "partOf": group_id}
        )
    with pytest.raises(RecordError):
        await create_record(
            ograg, TX, {"@type": "CadFile", "name": "x.step", "partOf": "missing"}
        )


async def test_an_update_changes_only_the_given_fields():
    ograg: OgRagService = make_service()
    machine_id, group_id, _ = await create_tree(ograg)

    await update_record(ograg, TX, group_id, {"name": " Tray ", "identifier": ""})

    group: Record = await get_record(ograg, TX, group_id)
    assert group.graph["name"] == "Tray"
    assert "identifier" not in group.graph
    assert group.graph["rootOf"] == machine_id


async def test_invalid_fields_are_refused():
    ograg: OgRagService = make_service()
    machine_id, group_id, _ = await create_tree(ograg)
    with pytest.raises(RecordError):
        await create_record(ograg, TX, {"@type": "Machine", "name": "  "})
    with pytest.raises(RecordError):
        await update_record(ograg, TX, machine_id, {"name": None, "identifier": None})
    with pytest.raises(RecordError):
        await update_record(ograg, TX, group_id, {"colour": "red"})
    # a link must still name a record of the right class
    with pytest.raises(RecordError):
        await update_record(ograg, TX, group_id, {"rootOf": group_id})
    with pytest.raises(NotFoundError):
        await update_record(ograg, TX, "missing", {"name": "x"})


async def test_an_update_is_a_json_merge_patch():
    ograg: OgRagService = make_service()
    machine_id, group_id, _ = await create_tree(ograg)
    other_id, _ = await create_record(
        ograg, TX, {"@type": "AssemblyGroup", "name": "Feeder", "rootOf": machine_id}
    )
    await update_record(ograg, TX, group_id, {"properties": {"path": "RC-01/AG"}})

    # nested objects merge key by key, null removes a key
    await update_record(ograg, TX, group_id, {"properties": {"path": None}})
    group: Record = await get_record(ograg, TX, group_id)
    # path was removed, properties object has no more keys so it is dropped
    assert "properties" not in group.graph
    # links are replaced as a whole
    await update_record(ograg, TX, group_id, {"rootOf": None, "partOf": [other_id]})
    moved: Record = await get_record(ograg, TX, group_id)
    assert (moved.graph.get("rootOf"), moved.graph["partOf"]) == (None, [other_id])


async def test_identifiers_may_be_shared():
    ograg: OgRagService = make_service()
    machine_id, _, _ = await create_tree(ograg)

    other_id, _ = await create_record(
        ograg, TX, {"@type": "Machine", "name": "Other", "identifier": "RC-01"}
    )

    assert await ograg.store.find_record_ids("Machine", "rc-01", TX) == sorted(
        [machine_id, other_id]
    )


async def test_deleting_a_machine_deletes_its_tree_and_keeps_knowledge():
    ograg: OgRagService = make_service()
    machine_id, group_id, cad_file_id = await create_tree(ograg)
    await add_item(ograg, group_id)

    tree: list[Record] = await lock_tree(ograg, TX, machine_id)
    assert tree[0].id == machine_id
    assert sorted(rec.id for rec in tree[1:]) == sorted([group_id, cad_file_id])
    result: DeleteResult = await delete_tree(ograg, TX, tree)

    assert result.deleted_ids == [rec.id for rec in reversed(tree)]
    assert result.marked_ids == [ITEM_ID]
    item: Record | None = await ograg.store.get_record(ITEM_ID)
    assert item is not None and item.review


async def test_deleting_a_group_deletes_the_groups_inside_it_first():
    ograg: OgRagService = make_service()
    _, group_id, _ = await create_tree(ograg)
    inner_id, _ = await create_record(
        ograg, TX, {"@type": "AssemblyGroup", "name": "Gripper", "partOf": group_id}
    )
    innermost_id, _ = await create_record(
        ograg, TX, {"@type": "AssemblyGroup", "name": "Finger", "partOf": inner_id}
    )

    tree: list[Record] = await lock_tree(ograg, TX, group_id)
    assert [rec.id for rec in tree] == [group_id, inner_id, innermost_id]
    result: DeleteResult = await delete_tree(ograg, TX, tree)
    assert result.deleted_ids == [innermost_id, inner_id, group_id]


async def test_records_written_by_the_generic_endpoint_are_handled():
    ograg: OgRagService = make_service()
    await ograg.upsert_record(
        "M-raw",
        {"@type": "Machine", "og:name": "Raw", "og:identifier": " RC-02 "},
    )

    await update_record(ograg, TX, "M-raw", {"identifier": None})
    raw: Record = await get_record(ograg, TX, "M-raw")
    assert raw.graph["name"] == "Raw"
    assert "identifier" not in raw.graph


def test_the_files_status_is_the_most_urgent_upload_status():
    assert get_files_status([]) is None
    ready, failed = UploadStatus.READY, UploadStatus.FAILED
    assert get_files_status([ready, ready]) == ready
    assert get_files_status([ready, failed]) == failed
    assert get_files_status([failed, UploadStatus.PROCESSING, ready]) == "processing"
    assert get_files_status([UploadStatus.PROCESSING, UploadStatus.UPLOADING]) == (
        "uploading"
    )


async def test_a_status_counts_only_the_file_records_pointing_straight_at_the_record():
    ograg: OgRagService = make_service(build_ontology_with(PART_OF_GROUP))
    machine_id, group_id, _ = await create_tree(ograg)
    group_file_id, _ = await create_record(
        ograg, TX, {"@type": "CadFile", "name": "tray.step", "partOfGroup": group_id}
    )
    catalog: CatalogService = make_catalog(ograg)
    await catalog.uploads.start_upload(group_file_id, "files/tray", 300, TX)

    assert await catalog.get_status(TX, group_id) == UploadStatus.UPLOADING
    # the group's file is no file of the machine
    assert await catalog.get_status(TX, machine_id) is None
    # the tree follows the same rule
    tree: TreeNode = await catalog.get_tree(TX, machine_id, depth=1)
    by_id: dict[str, TreeNode] = {child.record.id: child for child in tree.linked}
    assert (tree.status, by_id[group_id].status) == (None, UploadStatus.UPLOADING)


def get_shape(node: TreeNode) -> dict[str, object]:
    """The records linked to ``node`` by id, nested; dicts compare without order."""
    return {child.record.id: get_shape(child) for child in node.linked}


async def test_the_tree_holds_every_record_below_once_per_parent():
    ograg: OgRagService = make_service()
    machine_id, group_id, cad_file_id = await create_tree(ograg)
    inner_id, _ = await create_record(
        ograg, TX, {"@type": "AssemblyGroup", "name": "Gripper", "partOf": group_id}
    )
    await ograg.upsert_record(
        ITEM_ID,
        {
            "@type": "KnowledgeItem",
            "itemType": "lesson learned",
            "appliesTo": [inner_id],
            "appliesToMachine": [machine_id],
        },
    )
    catalog: CatalogService = make_catalog(ograg)

    tree: TreeNode = await catalog.get_tree(TX, machine_id)
    assert get_shape(tree) == {
        cad_file_id: {},
        group_id: {inner_id: {ITEM_ID: {}}},
        ITEM_ID: {},
    }
    assert [child.file for child in tree.linked if child.record.id == cad_file_id] == [
        True
    ]

    shallow: TreeNode = await catalog.get_tree(TX, group_id, depth=1)
    assert get_shape(shallow) == {inner_id: {}}
    with pytest.raises(NotFoundError):
        await catalog.get_tree(TX, "missing")


async def test_the_ancestors_lead_up_to_the_top_once_per_parent():
    ograg: OgRagService = make_service()
    machine_id, group_id, _ = await create_tree(ograg)
    inner_id, _ = await create_record(
        ograg, TX, {"@type": "AssemblyGroup", "name": "Gripper", "partOf": group_id}
    )
    await ograg.upsert_record(
        ITEM_ID,
        {
            "@type": "KnowledgeItem",
            "itemType": "lesson learned",
            "appliesTo": [inner_id],
            "appliesToMachine": [machine_id],
        },
    )
    catalog: CatalogService = make_catalog(ograg)

    ancestors: TreeNode = await catalog.get_ancestors(TX, ITEM_ID)
    assert get_shape(ancestors) == {
        inner_id: {group_id: {machine_id: {}}},
        machine_id: {},
    }
    near: TreeNode = await catalog.get_ancestors(TX, ITEM_ID, depth=1)
    assert get_shape(near) == {inner_id: {}, machine_id: {}}
    with pytest.raises(NotFoundError):
        await catalog.get_ancestors(TX, "missing")


async def test_a_record_never_appears_below_itself():
    """Old data may hold a loop: the tree stops where it would repeat an ancestor."""
    ograg: OgRagService = make_service()
    machine_id, _, _ = await create_tree(ograg)
    first: Record = Record(
        "AG-A",
        "AssemblyGroup",
        {"name": "A"},
        {},
        "v0",
        (Link("rootOf", machine_id), Link("partOf", "AG-B")),
    )
    second: Record = Record(
        "AG-B", "AssemblyGroup", {"name": "B"}, {}, "v0", (Link("partOf", "AG-A"),)
    )
    await ograg.store.save_records([first, second])

    tree: TreeNode = await make_catalog(ograg).get_tree(TX, machine_id)

    assert get_shape(tree)["AG-A"] == {"AG-B": {}}
    ancestors: TreeNode = await make_catalog(ograg).get_ancestors(TX, "AG-A")
    assert get_shape(ancestors) == {machine_id: {}, "AG-B": {}}
    # a loop of deleteWithParent links can't be sorted: only the record itself is deleted
    assert [rec.id for rec in await lock_tree(ograg, TX, machine_id)] == [machine_id]


async def test_a_record_with_another_parent_left_is_kept_with_what_hangs_below_it():
    ograg: OgRagService = make_service()
    machine_id, first_id, _ = await create_tree(ograg)
    second_id, _ = await create_record(
        ograg, TX, {"@type": "AssemblyGroup", "name": "Feeder", "rootOf": machine_id}
    )
    shared_id, _ = await create_record(
        ograg,
        TX,
        {"@type": "AssemblyGroup", "name": "Shared", "partOf": [first_id, second_id]},
    )
    below_id, _ = await create_record(
        ograg, TX, {"@type": "AssemblyGroup", "name": "Below", "partOf": shared_id}
    )

    tree: list[Record] = await lock_tree(ograg, TX, first_id)
    assert [rec.id for rec in tree] == [first_id]
    await delete_tree(ograg, TX, tree)
    shared: Record = await get_record(ograg, TX, shared_id)
    assert shared.graph["partOf"] == [second_id] and not shared.review

    # once the last such parent goes, it goes too, with what hangs below it
    whole: list[Record] = await lock_tree(ograg, TX, machine_id)
    assert {rec.id for rec in whole} >= {second_id, shared_id, below_id}
