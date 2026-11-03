from collections.abc import Sequence
from typing import Any, override

import pytest
from fakes import MemoryRecordStore, load_ontology, make_service
from helpers import assert_mentions

from services import ConflictError, Record, Tx, UnstorableValueError
from services.ograg.service import DeleteResult, OgRagService, RecordError

pytestmark = pytest.mark.anyio

MACHINE_ID: str = "RC-01"
GROUP_ID: str = "AG-IT-003"
ITEM_ID: str = "KI-1"
AUTHOR: str = "Jane"
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
    "partOf": MACHINE_ID,
}
ITEM: dict[str, Any] = {
    "@type": "KnowledgeItem",
    "itemType": "lesson learned",
    "scope": "machine-specific",
    "statement": "Chamfer the nest.",
    "appliesTo": [GROUP_ID],
}


async def get_stored_record(service: OgRagService, record_id: str) -> Record:
    """The get_stored_record record; fails the test if there is none."""
    record: Record | None = await service.store.get_record(record_id)
    assert record is not None, f"{record_id} is not get_stored_record"
    return record


async def create_loaded_service() -> OgRagService:
    service: OgRagService = make_service()
    await service.upsert_record(MACHINE_ID, MACHINE)
    await service.upsert_record(GROUP_ID, GROUP)
    await service.upsert_record(ITEM_ID, ITEM)
    return service


async def test_a_record_is_validated_and_stored():
    service: OgRagService = make_service()
    warnings: list[str] = await service.upsert_record(
        MACHINE_ID, {**MACHINE, **UNKNOWN}
    )
    assert len(warnings) == 1
    assert_mentions(warnings[0], "Machine", "colour")
    assert await service.get_records() == {MACHINE_ID: {**MACHINE, "@id": MACHINE_ID}}
    record: Record = await get_stored_record(service, MACHINE_ID)
    assert record.input["colour"] == UNKNOWN["colour"]  # input is kept as submitted
    assert record.ontology_version == service.ontology.version


async def test_type_defaults_to_the_anchor_class():
    service: OgRagService = make_service()
    await service.upsert_record(GROUP_ID, {"name": "Gripper"})
    assert (await get_stored_record(service, GROUP_ID)).cls == "AssemblyGroup"


@pytest.mark.parametrize(
    ("node", "keywords"),
    [
        ({"@type": "Characteristic", "function": "Feed parts"}, ("Characteristic",)),
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
    assert await service.get_records() == {}


async def test_a_link_to_a_missing_record_is_refused():
    service: OgRagService = make_service()
    with pytest.raises(RecordError) as raised:
        await service.upsert_record(GROUP_ID, GROUP)
    assert_mentions(str(raised.value), "partOf", MACHINE_ID)
    assert await service.get_records() == {}


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
    service: OgRagService = make_service()
    await service.upsert_record(
        ITEM_ID, {**ITEM, "appliesTo": [], "relatesTo": [ITEM_ID]}
    )
    record: Record = await get_stored_record(service, ITEM_ID)
    assert [link.target_id for link in record.links] == [ITEM_ID]


async def test_a_record_linking_to_itself_can_be_deleted():
    service: OgRagService = make_service()
    await service.upsert_record(
        ITEM_ID, {**ITEM, "appliesTo": [], "relatesTo": [ITEM_ID]}
    )
    result: DeleteResult = await service.delete_record(ITEM_ID)
    assert result == DeleteResult(deleted_ids=[ITEM_ID], marked_ids=[])
    assert await service.get_records() == {}


async def test_the_author_replaces_what_the_node_says():
    service: OgRagService = make_service()
    item: dict[str, Any] = {**ITEM, "appliesTo": [], "author": "someone else"}
    await service.upsert_record(ITEM_ID, item, author=AUTHOR)
    assert (await get_stored_record(service, ITEM_ID)).graph["author"] == AUTHOR


async def test_text_the_store_cannot_keep_is_refused_and_nothing_is_written():
    service: OgRagService = await create_loaded_service()
    with pytest.raises(UnstorableValueError):
        await service.upsert_record("RC-02", {**MACHINE, "name": "nul \x00 byte"})
    assert sorted(await service.get_records()) == [GROUP_ID, ITEM_ID, MACHINE_ID]


async def test_delete_marks_records_that_lost_their_last_parent_link():
    service: OgRagService = await create_loaded_service()
    result: DeleteResult = await service.delete_record(GROUP_ID)
    assert (result.deleted_ids, result.marked_ids) == ([GROUP_ID], [ITEM_ID])
    item: Record = await get_stored_record(service, ITEM_ID)
    # unlinked in graph and input:
    assert "appliesTo" not in item.graph and "appliesTo" not in item.input
    assert_mentions(item.review, "AssemblyGroup", GROUP_ID)
    assert [rec.id for rec in await service.get_records_to_review()] == [ITEM_ID]

    await service.upsert_record(
        ITEM_ID, {**ITEM, "appliesTo": []}
    )  # saving clears the review
    assert await service.get_records_to_review() == []


async def test_delete_orphans_deletes_them_recursively():
    service: OgRagService = await create_loaded_service()
    result: DeleteResult = await service.delete_record(MACHINE_ID, delete_orphans=True)
    assert (result.deleted_ids, result.marked_ids) == (
        [MACHINE_ID, GROUP_ID, ITEM_ID],
        [],
    )
    assert await service.get_records() == {}


async def test_a_record_with_another_parent_link_left_is_not_marked():
    service: OgRagService = await create_loaded_service()
    await service.upsert_record(ITEM_ID, {**ITEM, "appliesToMachine": [MACHINE_ID]})
    result: DeleteResult = await service.delete_record(GROUP_ID)
    assert result.marked_ids == []
    item: Record = await get_stored_record(service, ITEM_ID)
    assert item.graph["appliesToMachine"] == [MACHINE_ID]


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
    assert MACHINE_ID in await service.get_records()


async def test_a_conflict_in_the_callers_transaction_is_raised_at_once():
    service = OgRagService(load_ontology(), FlakyStore(failures=1))
    with pytest.raises(ConflictError):
        await service.upsert_record(MACHINE_ID, MACHINE, tx="your session")
