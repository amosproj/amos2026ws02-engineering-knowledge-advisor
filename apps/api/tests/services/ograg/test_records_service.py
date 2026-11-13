from collections.abc import Sequence
from typing import Any, override

import pytest
from fakes import MemoryRecordStore, build_ontology_with, load_ontology, make_service
from helpers import assert_mentions

from services import ConflictError, Json, Record, Tx, UnstorableValueError
from services.ograg.service import (
    DeleteResult,
    OgRagService,
    ParentLimitError,
    RecordError,
)

pytestmark = pytest.mark.anyio

MACHINE_ID: str = "RC-01"
GROUP_ID: str = "AG-IT-003"
INSTANCE_ID: str = "AI-1"
ITEM_ID: str = "KI-1"
UNKNOWN: dict[str, str] = {"colour": "red"}  # property the ontology does not define

MACHINE: dict[str, Any] = {
    "@type": "Machine",
    "identifier": MACHINE_ID,
    "name": "Robot cell",
}
GROUP: dict[str, Any] = {
    "@type": "AssemblyGroup",
    "identifier": GROUP_ID,
    "name": "Input tray",
    "definedIn": MACHINE_ID,
}
INSTANCE: dict[str, Any] = {
    "@type": "AssemblyInstance",
    "name": "Input tray:1",
    "instanceOf": GROUP_ID,
    "rootOf": MACHINE_ID,
}
ITEM: dict[str, Any] = {
    "@type": "KnowledgeItem",
    "itemType": "lesson learned",
    "properties": {"name": "Chamfer", "statement": "Chamfer the nest."},
    "appliesTo": [GROUP_ID],
}
# not in the ontology file: added where a test needs them
RELATES_TO: dict[str, Any] = {
    "@id": "og:relatesTo",
    "@type": "rdf:Property",
    "domain": "og:KnowledgeItem",
    "range": "og:KnowledgeItem",
}


def instance(name: str, parent_ids: Json) -> dict[str, Any]:
    return {
        "@type": "AssemblyInstance",
        "name": name,
        "instanceOf": GROUP_ID,
        "partOf": parent_ids,
    }


async def get_all_record_ids(service: OgRagService) -> list[str]:
    return [str(rec["@id"]) for rec in await service.get_records()]


async def get_stored_record(service: OgRagService, record_id: str) -> Record:
    """The get_stored_record record; fails the test if there is none."""
    record: Record | None = await service.store.get_record(record_id)
    assert record is not None, f"{record_id} is not get_stored_record"
    return record


async def create_loaded_service() -> OgRagService:
    service: OgRagService = make_service()
    await service.upsert_record(MACHINE_ID, MACHINE)
    await service.upsert_record(GROUP_ID, GROUP)
    await service.upsert_record(INSTANCE_ID, INSTANCE)
    await service.upsert_record(ITEM_ID, ITEM)
    return service


async def test_a_record_is_validated_and_stored():
    service: OgRagService = make_service()
    warnings: list[str] = await service.upsert_record(
        MACHINE_ID, {**MACHINE, **UNKNOWN}
    )
    assert len(warnings) == 1
    assert_mentions(warnings[0], "Machine", "colour")
    assert await service.get_records() == [{**MACHINE, "@id": MACHINE_ID}]
    record: Record = await get_stored_record(service, MACHINE_ID)
    assert record.input["colour"] == UNKNOWN["colour"]  # input is kept as submitted
    assert record.ontology_version == service.ontology.version


async def test_returned_records_have_id():
    store = MemoryRecordStore()
    await store.save_records(
        [Record(MACHINE_ID, "Machine", dict(MACHINE), dict(MACHINE), "v0")]
    )
    service: OgRagService = make_service(store=store)
    assert await service.get_records() == [{**MACHINE, "@id": MACHINE_ID}]


async def test_type_defaults_to_the_anchor_class():
    service: OgRagService = make_service()
    await service.upsert_record(GROUP_ID, {"name": "Gripper"})
    assert (await get_stored_record(service, GROUP_ID)).cls == "AssemblyGroup"


@pytest.mark.parametrize(
    ("node", "keywords"),
    [
        ({"@type": "AssemblyProperties", "sizeX": 0.8}, ("AssemblyProperties",)),
        ({"@type": "Machine", **UNKNOWN}, ("Machine", "colour")),
        ({"@type": "Machine"}, ("Machine",)),
    ],
)
async def test_records_that_do_not_fit_are_refused(
    node: dict[str, Any], keywords: tuple[str, ...]
):
    service: OgRagService = make_service()
    with pytest.raises(RecordError) as raised:
        await service.upsert_record("X-1", node)
    assert_mentions(str(raised.value), *keywords)
    assert await service.get_records() == []


@pytest.mark.parametrize(
    "identity",
    [{}, {"name": "  "}, {"name": ["", " "]}],
    ids=["missing", "blank", "blank list"],
)
async def test_a_record_without_an_identity_value_is_refused(
    identity: dict[str, Any],
):
    service: OgRagService = make_service()
    group: dict[str, Any] = {
        "@type": "AssemblyGroup",
        "description": "Feeds the parts.",
        **identity,
    }
    with pytest.raises(RecordError) as raised:
        await service.upsert_record(GROUP_ID, group)
    assert_mentions(str(raised.value), "AssemblyGroup", "name")
    assert await service.get_records() == []


async def test_a_class_without_identity_properties_needs_no_name():
    service: OgRagService = make_service()
    await service.upsert_record("GL-1", {"@type": "Guideline", "description": "x"})
    assert await get_all_record_ids(service) == ["GL-1"]


async def test_one_identity_value_is_enough():
    service: OgRagService = make_service()
    await service.upsert_record(MACHINE_ID, {"@type": "Machine", "identifier": "x"})
    assert [rec["@id"] for rec in await service.get_records()] == [MACHINE_ID]


async def test_a_link_to_a_missing_record_is_refused():
    service: OgRagService = make_service()
    with pytest.raises(RecordError) as raised:
        await service.upsert_record(GROUP_ID, GROUP)
    assert_mentions(str(raised.value), "definedIn", MACHINE_ID)
    assert await service.get_records() == []


async def test_a_link_to_a_record_of_the_wrong_class_is_refused():
    service: OgRagService = await create_loaded_service()
    with pytest.raises(RecordError) as raised:
        await service.upsert_record("KI-2", {**ITEM, "appliesTo": [MACHINE_ID]})
    assert_mentions(
        str(raised.value), "appliesTo", MACHINE_ID, "Machine", "AssemblyGroup"
    )


async def test_an_id_keeps_its_class():
    service: OgRagService = await create_loaded_service()
    group: dict[str, Any] = {"@type": "AssemblyGroup", "name": "Not a machine"}
    with pytest.raises(RecordError) as raised:
        await service.upsert_record(MACHINE_ID, group)
    assert_mentions(str(raised.value), MACHINE_ID, "Machine", "AssemblyGroup")


async def test_a_record_may_link_to_itself():
    service: OgRagService = make_service(build_ontology_with(RELATES_TO))
    await service.upsert_record(
        ITEM_ID, {**ITEM, "appliesTo": [], "relatesTo": [ITEM_ID]}
    )
    record: Record = await get_stored_record(service, ITEM_ID)
    assert [link.target_id for link in record.links] == [ITEM_ID]


async def test_a_record_linking_to_itself_can_be_deleted():
    service: OgRagService = make_service(build_ontology_with(RELATES_TO))
    await service.upsert_record(
        ITEM_ID, {**ITEM, "appliesTo": [], "relatesTo": [ITEM_ID]}
    )
    result: DeleteResult = await service.delete_record(ITEM_ID)
    assert result == DeleteResult(deleted_ids=[ITEM_ID], marked_ids=[])
    assert await service.get_records() == []


async def test_text_the_store_cannot_keep_is_refused_and_nothing_is_written():
    service: OgRagService = await create_loaded_service()
    with pytest.raises(UnstorableValueError):
        await service.upsert_record("RC-02", {**MACHINE, "name": "nul \x00 byte"})
    assert await get_all_record_ids(service) == [
        GROUP_ID,
        INSTANCE_ID,
        ITEM_ID,
        MACHINE_ID,
    ]


async def test_delete_marks_records_that_lost_their_last_parent_link():
    service: OgRagService = await create_loaded_service()
    result: DeleteResult = await service.delete_record(GROUP_ID)
    assert (result.deleted_ids, result.marked_ids) == ([GROUP_ID], [ITEM_ID])
    item: Record = await get_stored_record(service, ITEM_ID)
    # unlinked in graph and input:
    assert "appliesTo" not in item.graph and "appliesTo" not in item.input
    assert_mentions(item.review, "AssemblyGroup", GROUP_ID)
    assert [rec.id for rec in await service.get_records_to_review()] == [ITEM_ID]
    # its instances stay in the tree without it
    kept: Record = await get_stored_record(service, INSTANCE_ID)
    assert "instanceOf" not in kept.graph and kept.graph["rootOf"] == MACHINE_ID

    await service.upsert_record(
        ITEM_ID, {**ITEM, "appliesTo": []}
    )  # saving clears the review
    assert await service.get_records_to_review() == []


async def test_delete_orphans_deletes_them_recursively():
    service: OgRagService = await create_loaded_service()
    result: DeleteResult = await service.delete_record(MACHINE_ID, delete_orphans=True)
    assert (result.deleted_ids, result.marked_ids) == (
        [MACHINE_ID, GROUP_ID, INSTANCE_ID, ITEM_ID],
        [],
    )
    assert await service.get_records() == []


async def test_a_record_with_another_parent_link_left_is_not_marked():
    service: OgRagService = await create_loaded_service()
    await service.upsert_record(ITEM_ID, {**ITEM, "appliesToMachine": [MACHINE_ID]})
    result: DeleteResult = await service.delete_record(GROUP_ID)
    assert result.marked_ids == []
    item: Record = await get_stored_record(service, ITEM_ID)
    assert item.graph["appliesToMachine"] == [MACHINE_ID]


async def test_assembly_instances_form_a_tree():
    service: OgRagService = await create_loaded_service()
    await service.upsert_record("AI-2", instance("Gripper", INSTANCE_ID))
    await service.upsert_record("AI-3", instance("Finger", ["AI-2"]))
    finger: Record = await get_stored_record(service, "AI-3")
    assert finger.graph["partOf"] == ["AI-2"]
    # moving an instance within the tree is fine
    await service.upsert_record("AI-3", instance("Finger", INSTANCE_ID))


async def test_a_machine_takes_one_root_instance():
    service: OgRagService = await create_loaded_service()
    with pytest.raises(ParentLimitError) as raised:
        await service.upsert_record("AI-2", {**INSTANCE, "name": "Second root"})
    assert_mentions(str(raised.value), MACHINE_ID, "AssemblyInstance", "rootOf")


def cad_file(machine_id: str) -> dict[str, Any]:
    return {"@type": "CadFile", "name": "cell.step", "partOf": machine_id}


async def test_a_machine_takes_one_cad_file():
    service: OgRagService = await create_loaded_service()
    await service.upsert_record("CF-1", cad_file(MACHINE_ID))
    with pytest.raises(ParentLimitError) as raised:
        await service.upsert_record("CF-2", cad_file(MACHINE_ID))
    assert raised.value.error_code == "max_per_parent"
    assert_mentions(str(raised.value), MACHINE_ID, "CadFile", "partOf")
    assert await service.store.get_record("CF-2") is None

    await service.upsert_record("CF-1", {**cad_file(MACHINE_ID), "name": "v2.step"})


async def test_a_cad_file_moves_only_to_a_machine_without_one():
    service: OgRagService = await create_loaded_service()
    await service.upsert_record("RC-02", {**MACHINE, "identifier": "RC-02"})
    await service.upsert_record("CF-1", cad_file(MACHINE_ID))
    await service.upsert_record("CF-2", cad_file("RC-02"))
    with pytest.raises(ParentLimitError):
        await service.upsert_record("CF-2", cad_file(MACHINE_ID))

    await service.delete_record("CF-1")
    await service.upsert_record("CF-2", cad_file(MACHINE_ID))


@pytest.mark.parametrize(
    ("record_id", "parent_ids"),
    [(INSTANCE_ID, ["AI-3"]), ("AI-2", ["AI-2"]), ("AI-2", [INSTANCE_ID, "AI-3"])],
    ids=["through the tree", "itself", "one of several parents"],
)
async def test_an_instance_cannot_become_its_own_ancestor(
    record_id: str, parent_ids: list[Json]
):
    service: OgRagService = await create_loaded_service()
    await service.upsert_record("AI-2", instance("Gripper", INSTANCE_ID))
    await service.upsert_record("AI-3", instance("Finger", "AI-2"))
    with pytest.raises(RecordError) as raised:
        await service.upsert_record(record_id, instance("Moved", parent_ids))
    assert_mentions(str(raised.value), record_id, "ancestor", "partOf")
    assert (await get_stored_record(service, record_id)).graph["name"] != "Moved"


async def test_a_batch_links_its_records_in_any_order():
    service: OgRagService = make_service()
    await service.upsert_record(MACHINE_ID, MACHINE)
    warnings: list[str] = await service.upsert_records(
        {
            "AI-2": instance("Gripper", INSTANCE_ID),
            INSTANCE_ID: INSTANCE,
            GROUP_ID: {**GROUP, **UNKNOWN},
        }
    )
    assert len(warnings) == 1
    assert sorted(await get_all_record_ids(service)) == sorted(
        ["AI-2", INSTANCE_ID, GROUP_ID, MACHINE_ID]
    )


@pytest.mark.parametrize(
    "nodes",
    [
        {GROUP_ID: GROUP, INSTANCE_ID: {**INSTANCE, "instanceOf": "AG-missing"}},
        {GROUP_ID: GROUP, INSTANCE_ID: {**INSTANCE, "instanceOf": "AI-2"}},
        {GROUP_ID: GROUP, MACHINE_ID: GROUP},
        {GROUP_ID: GROUP, INSTANCE_ID: {"@type": "AssemblyInstance"}},
    ],
    ids=["missing target", "target of the wrong class", "class change", "invalid"],
)
async def test_a_batch_is_refused_as_a_whole(nodes: dict[str, dict[str, Any]]):
    service: OgRagService = make_service()
    await service.upsert_record(MACHINE_ID, MACHINE)
    with pytest.raises(RecordError):
        await service.upsert_records(
            {"AI-2": instance("Gripper", INSTANCE_ID), **nodes}
        )
    assert await get_all_record_ids(service) == [MACHINE_ID]


async def test_a_batch_counts_its_own_records_against_the_parent_limit():
    service: OgRagService = make_service()
    await service.upsert_record(MACHINE_ID, MACHINE)
    await service.upsert_record(GROUP_ID, GROUP)
    with pytest.raises(ParentLimitError):
        await service.upsert_records({INSTANCE_ID: INSTANCE, "AI-2": INSTANCE})
    assert await service.store.get_record(INSTANCE_ID) is None


async def test_a_batch_counts_the_stored_records_against_the_parent_limit():
    service: OgRagService = await create_loaded_service()
    with pytest.raises(ParentLimitError):
        await service.upsert_records({"AI-2": INSTANCE})
    # the stored root keeps its place, a repeated link counts once
    await service.upsert_records(
        {INSTANCE_ID: {**INSTANCE, "rootOf": [MACHINE_ID, MACHINE_ID]}}
    )


@pytest.mark.parametrize(
    "nodes",
    [
        {"AI-2": instance("Gripper", "AI-2")},
        {"AI-2": instance("Gripper", "AI-3"), "AI-3": instance("Finger", "AI-2")},
        {
            "AI-2": instance("Gripper", INSTANCE_ID),
            INSTANCE_ID: instance("Root", "AI-2"),
        },
    ],
    ids=["itself", "within the batch", "through a stored record"],
)
async def test_a_batch_cannot_make_a_record_its_own_ancestor(
    nodes: dict[str, dict[str, Any]],
):
    service: OgRagService = await create_loaded_service()
    with pytest.raises(RecordError) as raised:
        await service.upsert_records(nodes)
    assert_mentions(str(raised.value), "ancestor", "partOf")
    assert await service.store.get_record("AI-2") is None


async def test_deleting_a_missing_record_deletes_nothing():
    result: DeleteResult = await make_service().delete_record("nope")
    assert result.deleted_ids == []


class FlakyStore(MemoryRecordStore):
    """Fails the first ``failures`` saves with a ``ConflictError``, like a deadlock."""

    def __init__(self, failures: int, identity: dict[str, list[str]] | None = None):
        super().__init__(identity)
        self.failures: int = failures

    @override
    async def save_records(
        self, records: Sequence[Record], tx: Tx | None = None
    ) -> None:
        if self.failures:
            self.failures -= 1
            raise ConflictError("deadlock")
        await super().save_records(records, tx)


async def test_a_conflict_is_retried_in_the_services_own_transaction():
    service = OgRagService(load_ontology(), FlakyStore(failures=2))
    await service.upsert_record(MACHINE_ID, MACHINE)
    assert MACHINE_ID in await get_all_record_ids(service)


async def test_a_conflict_in_the_callers_transaction_is_raised_at_once():
    service = OgRagService(load_ontology(), FlakyStore(failures=1))
    with pytest.raises(ConflictError):
        await service.upsert_record(MACHINE_ID, MACHINE, tx="your session")
