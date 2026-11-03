from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import pytest

from services import Link, Record, RecordLinkedError, RecordStore, UnstorableValueError

IDENTITY_PROPERTY_NAMES: dict[str, list[str]] = {
    "Machine": ["identifier", "name"],
    "AssemblyGroup": ["identifier", "name"],
}
MACHINE_ID: str = "M-1"
GROUP_ID: str = "AG-1"
TWIN_ID: str = "AG-2"  # a second group with the same name, in other case
ITEM_ID: str = "KI-1"
OTHER_ITEM_ID: str = "KI-2"
ORPHAN_ID: str = "KI-3"
STATEMENT: str = "Chamfer it."
UNSTORABLE_TEXTS: tuple[str, ...] = ("nul \x00 byte", "broken \ud800 half")


def build_record(
    record_id: str,
    cls: str,
    links: Sequence[tuple[str, str]] = (),
    review: str = "",
    **props: str | list[str],
) -> Record:
    graph: dict[str, Any] = {"@type": cls, "@id": record_id, **props}
    for prop, target in links:
        graph.setdefault(prop, []).append(target)
    return Record(
        id=record_id,
        cls=cls,
        graph=graph,
        input=graph,
        ontology_version="v1",
        links=tuple(Link(prop, target) for prop, target in links),
        review=review,
    )


async def get_stored_record(store: RecordStore, record_id: str) -> Record:
    """The get_stored_record build_record; fails the check if there is none."""
    found: Record | None = await store.get_record(record_id)
    assert found is not None, f"{record_id} is not get_stored_record"
    return found


MACHINE: Record = build_record(
    MACHINE_ID, "Machine", identifier="RC-01", name="Robot cell"
)
GROUP: Record = build_record(
    GROUP_ID,
    "AssemblyGroup",
    [("partOf", MACHINE_ID)],
    identifier="AG-IT-003",
    name="Input tray",
)


async def check_links_are_saved_and_found_from_their_target(store: RecordStore) -> None:
    item: Record = build_record(
        ITEM_ID,
        "KnowledgeItem",
        [("appliesTo", GROUP_ID), ("relatesTo", OTHER_ITEM_ID)],
        statement=STATEMENT,
    )
    other: Record = build_record(
        OTHER_ITEM_ID, "KnowledgeItem", [("appliesTo", GROUP_ID)], statement="Guide it."
    )
    await store.save_records([MACHINE, GROUP, item, other])
    assert (await get_stored_record(store, ITEM_ID)).links == (
        Link("appliesTo", GROUP_ID),
        Link("relatesTo", OTHER_ITEM_ID),
    )
    assert [rec.id for rec in await store.get_linking_records([GROUP_ID])] == [
        ITEM_ID,
        OTHER_ITEM_ID,
    ]
    linking_either: list[Record] = await store.get_linking_records(
        [MACHINE_ID, OTHER_ITEM_ID]
    )
    assert [rec.id for rec in linking_either] == [GROUP_ID, ITEM_ID]

    # Links are replaced on save:
    await store.save_records(
        [build_record(ITEM_ID, "KnowledgeItem", statement=STATEMENT)]
    )
    assert (await get_stored_record(store, ITEM_ID)).links == ()
    assert [rec.id for rec in await store.get_linking_records([GROUP_ID])] == [
        OTHER_ITEM_ID
    ]


async def check_deleting_a_linked_target_is_refused_by_the_store(
    store: RecordStore,
) -> None:
    await store.save_records([MACHINE, GROUP])
    with pytest.raises(RecordLinkedError, match=GROUP_ID):
        await store.delete_record(MACHINE_ID)
    assert await store.get_record(MACHINE_ID) is not None
    assert await store.delete_record(GROUP_ID)  # source's links deleted too
    assert await store.delete_record(MACHINE_ID)
    assert not await store.delete_record(MACHINE_ID)


async def check_a_record_linking_to_itself_can_be_deleted(store: RecordStore) -> None:
    item: Record = build_record(
        ITEM_ID, "KnowledgeItem", [("relatesTo", ITEM_ID)], statement=STATEMENT
    )
    await store.save_records([item])
    assert await store.delete_record(ITEM_ID)
    assert await store.get_record(ITEM_ID) is None
    assert await store.get_linking_records([ITEM_ID]) == []


async def check_find_matches_identity_case_insensitively(store: RecordStore) -> None:
    twin: Record = build_record(
        TWIN_ID,
        "AssemblyGroup",
        [("partOf", MACHINE_ID)],
        identifier="AG-IT-004",
        name="input TRAY",
    )
    await store.save_records([MACHINE, GROUP, twin])
    find = store.find_record_ids
    assert await find("AssemblyGroup", "INPUT tray") == [GROUP_ID, TWIN_ID]  # ambiguous
    assert await find("AssemblyGroup", "ag-it-003") == [GROUP_ID]
    assert await find("AssemblyGroup", TWIN_ID.lower()) == [
        TWIN_ID
    ]  # the id counts too
    assert await find("Machine", "Input tray") == []
    assert await find("AssemblyGroup", "Input") == []  # equal, not contained


async def check_find_matches_any_value_of_a_list(store: RecordStore) -> None:
    listed: Record = build_record(
        TWIN_ID,
        "AssemblyGroup",
        [("partOf", MACHINE_ID)],
        identifier=["AG-IT-005", "AG-IT-005-OLD"],
        name=["Feed tray", "Input TRAY"],
    )
    await store.save_records([MACHINE, GROUP, listed])
    find = store.find_record_ids
    assert await find("AssemblyGroup", "ag-it-005") == [TWIN_ID]
    assert await find("AssemblyGroup", "AG-IT-005-old") == [TWIN_ID]
    assert await find("AssemblyGroup", "feed TRAY") == [TWIN_ID]
    assert await find("AssemblyGroup", "input tray") == [GROUP_ID, TWIN_ID]  # one each
    assert await find("AssemblyGroup", "AG-IT") == []  # equal, not contained
    assert await find("AssemblyGroup", "AG-IT-005-OLD, AG-IT-005") == []  # no list text
    assert await find("Machine", "feed tray") == []


async def check_find_follows_the_identity_of_the_last_save(store: RecordStore) -> None:
    await store.save_records([MACHINE, GROUP])
    renamed: Record = build_record(
        GROUP_ID,
        "AssemblyGroup",
        [("partOf", MACHINE_ID)],
        identifier="AG-IT-003",
        name=["Output tray", "Exit tray"],
    )
    await store.save_records([renamed])
    find = store.find_record_ids
    assert await find("AssemblyGroup", "Input tray") == []
    assert await find("AssemblyGroup", "exit TRAY") == [GROUP_ID]
    assert await find("AssemblyGroup", "ag-it-003") == [GROUP_ID]
    assert await store.delete_record(GROUP_ID)
    assert await find("AssemblyGroup", "ag-it-003") == []


async def check_needs_review_lists_marked_records(store: RecordStore) -> None:
    orphan: Record = build_record(
        ORPHAN_ID,
        "KnowledgeItem",
        review="Lost its last link: AssemblyGroup AG-7 was deleted.",
        statement="x",
    )
    await store.save_records([MACHINE, orphan])
    marked: list[Record] = await store.get_records_to_review()
    assert [(rec.id, rec.review) for rec in marked] == [(ORPHAN_ID, orphan.review)]
    await store.save_records([build_record(ORPHAN_ID, "KnowledgeItem", statement="x")])
    assert await store.get_records_to_review() == []


async def check_text_the_database_cannot_store_is_refused(store: RecordStore) -> None:
    for bad in UNSTORABLE_TEXTS:
        with pytest.raises(UnstorableValueError):
            await store.save_records([build_record("M-9", "Machine", name=bad)])
        with pytest.raises(UnstorableValueError):
            await store.get_record(f"M-{bad}")
    assert await store.get_all_records() == []  # nothing of a refused write is kept


Check = Callable[[RecordStore], Awaitable[None]]
CHECKS: list[Check] = [
    check_links_are_saved_and_found_from_their_target,
    check_deleting_a_linked_target_is_refused_by_the_store,
    check_a_record_linking_to_itself_can_be_deleted,
    check_find_matches_identity_case_insensitively,
    check_find_matches_any_value_of_a_list,
    check_find_follows_the_identity_of_the_last_save,
    check_needs_review_lists_marked_records,
    check_text_the_database_cannot_store_is_refused,
]
CHECK_IDS: list[str] = [check.__name__.removeprefix("check_") for check in CHECKS]
