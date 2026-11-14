"""Records of any record class, created, changed and deleted along the ontology's parent links.

Every function runs in the caller's transaction and does not commit: a failure must roll back the
whole operation.
"""

from collections.abc import Collection, Mapping, Sequence
from graphlib import CycleError, TopologicalSorter
from uuid import uuid4

from services import Json, JsonObject, Record, Tx
from services.catalog.errors import NotFoundError
from services.ograg.ontology import Ontology, get_local_name
from services.ograg.service import DeleteResult, OgRagService, RecordError

ERROR_NOT_FOUND: str = "no record {record_id!r}"
ERROR_NOT_FOUND_OF_CLASS: str = "no {cls} {record_id!r}"
ERROR_UNKNOWN_PROPERTY: str = "{cls} has no property {field!r}"

type Fields = Mapping[str, Json]


async def create_record(
    ograg: OgRagService,
    tx: Tx,
    node: Mapping[str, Json],
) -> tuple[str, list[str]]:
    """Stores ``node`` as a new record. Returns created id and validation warnings."""
    record_id: str = uuid4().hex
    warnings: list[str] = await ograg.upsert_record(record_id, node, tx)
    return record_id, warnings


async def update_record(
    ograg: OgRagService,
    tx: Tx,
    record_id: str,
    changes: Fields,
    expected_versions: Collection[str] | None = None,
) -> list[str]:
    """Applies ``changes`` to the stored record as a JSON Merge Patch (RFC 7396), then validates the whole record.

    Nested objects are merged key by key. Anything else, links and lists included, replaces the stored value. ``None``
    or blank text removes a key.

    Args:
        ograg: record service.
        tx: transaction.
        record_id: record to change.
        changes: properties of the record's class -> new value.
        expected_versions: versions to match (``OgRagService.check_version``).

    Returns:
        Validation warnings.

    Raises:
        NotFoundError: no record ``record_id``.
        RecordError: a key is not a property of the record's class, or the result is invalid.
        StaleVersionError: record has none of ``expected_versions``.
    """
    # the row lock makes concurrent updates of this record wait instead of overwriting each other
    await ograg.store.lock_record(record_id, tx)
    record: Record = await get_record(ograg, tx, record_id)
    for field in changes:
        if (record.cls, get_local_name(field)) not in ograg.ontology.properties:
            raise RecordError(
                ERROR_UNKNOWN_PROPERTY.format(cls=record.cls, field=field)
            )

    return await ograg.upsert_record(
        record_id, patch_input(record, changes), tx, expected_versions
    )


def patch_input(record: Record, changes: Fields) -> JsonObject:
    """The record's input with ``changes`` applied as in ``update_record``"""
    node: Json = _merge_patch(_to_local_names(record.input), dict(changes))
    assert isinstance(node, dict)  # a patch object merged into an object
    return node


async def get_record(
    ograg: OgRagService, tx: Tx, record_id: str, cls: str | None = None
) -> Record:
    """Returns the record ``record_id``.

    Raises:
        NotFoundError: no such record, or it is not a ``cls`` (if given).
    """
    record: Record | None = await ograg.store.get_record(record_id, tx)
    if record is None or (cls is not None and record.cls != cls):
        message: str = (
            ERROR_NOT_FOUND.format(record_id=record_id)
            if cls is None
            else ERROR_NOT_FOUND_OF_CLASS.format(cls=cls, record_id=record_id)
        )
        raise NotFoundError(message)
    return record


async def get_children(
    ograg: OgRagService,
    tx: Tx,
    parent_ids: Sequence[str],
    *,
    dependents_only: bool = False,
) -> list[Record]:
    """Returns the records whose parent links point to any of ``parent_ids``, sorted by id.

    Args:
        ograg: record service.
        tx: transaction.
        parent_ids: ids of the parents.
        dependents_only: only parent links marked ``og:deleteWithParent`` count.
    """
    if not parent_ids:
        return []
    targets: set[str] = set(parent_ids)
    linking: list[Record] = await ograg.store.get_linking_records(parent_ids, tx)
    return [
        rec
        for rec in linking
        if any(
            link.target_id in targets
            and link.property_name
            in _get_parent_link_names(ograg.ontology, rec.cls, dependents_only)
            for link in rec.links
        )
    ]


async def lock_tree(ograg: OgRagService, tx: Tx, record_id: str) -> list[Record]:
    """Locks the record and everything deleted with it, top-down. Returns them parents first.

    A parent is locked before its children are listed, so no child can be added meanwhile.
    A record goes with the tree only if all its ``og:deleteWithParent`` links point into it: one with such a parent
    outside the tree stays, and so does what hangs only below it.

    Raises:
        NotFoundError: no record ``record_id``.
    """
    await ograg.store.lock_record(record_id, tx)
    tree: list[Record] = [await get_record(ograg, tx, record_id)]
    seen_ids: set[str] = {record_id}
    position: int = 0
    while position < len(tree):
        parent: Record = tree[position]
        position += 1
        for child in await get_children(ograg, tx, [parent.id], dependents_only=True):
            if child.id in seen_ids:
                continue
            await ograg.store.lock_record(child.id, tx)
            seen_ids.add(child.id)
            tree.append(child)
    return _drop_records_with_other_parents(ograg.ontology, tree)


async def delete_tree(
    ograg: OgRagService,
    tx: Tx,
    tree: Sequence[Record],
    delete_orphans: bool = False,
) -> DeleteResult:
    """Deletes the records of ``tree`` (from ``lock_tree``), children first.

    Records that lose their last parent link otherwise are marked for review, or deleted if
    ``delete_orphans`` is ``True``.
    """
    result = DeleteResult()
    for rec in reversed(tree):
        deleted: DeleteResult = await ograg.delete_record(
            rec.id, tx, delete_orphans=delete_orphans
        )
        result.deleted_ids.extend(deleted.deleted_ids)
        result.marked_ids.extend(deleted.marked_ids)
    return result


def _drop_records_with_other_parents(
    onto: Ontology, tree: list[Record]
) -> list[Record]:
    """Returns ``tree`` without the records that keep an ``og:deleteWithParent`` parent outside it, and without what
    hangs only below those. The first record stays; the rest come parents first.

    One pass over the records sorted parents first: a record stays in the tree if all its such parents do. A loop of
    such links (old data) can't be sorted: then only the first record is returned, nothing is deleted with it.
    """
    root: Record = tree[0]
    by_id: dict[str, Record] = {rec.id: rec for rec in tree}
    parent_ids_by_id: dict[str, set[str]] = {
        rec.id: {
            link.target_id
            for link in rec.links
            if link.property_name in onto.get_delete_with_parent_names(rec.cls)
        }
        for rec in tree[1:]
    }
    try:
        ordered_ids: list[str] = list(
            TopologicalSorter(
                {
                    record_id: parent_ids & by_id.keys()
                    for record_id, parent_ids in parent_ids_by_id.items()
                }
            ).static_order()
        )
    except CycleError:
        return [root]
    kept_ids: set[str] = {root.id}
    for record_id in ordered_ids:
        if record_id != root.id and parent_ids_by_id[record_id] <= kept_ids:
            kept_ids.add(record_id)
    return [root] + [
        by_id[record_id]
        for record_id in ordered_ids
        if record_id != root.id and record_id in kept_ids
    ]


def _get_parent_link_names(onto: Ontology, cls: str, dependents_only: bool) -> set[str]:
    if dependents_only:
        return onto.get_delete_with_parent_names(cls)
    return onto.get_parent_link_names(cls)


def _to_local_names(value: Json) -> Json:
    """Returns ``value`` with every object key as its local name, e.g. ``og:name`` as ``name``, at any depth."""
    if isinstance(value, dict):
        return {get_local_name(key): _to_local_names(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_to_local_names(val) for val in value]
    return value


def _merge_patch(target: Json, patch: Json) -> Json:
    """Returns ``target`` changed by ``patch`` (RFC 7396): objects merge key by key, anything else replaces.

    ``None`` or blank text removes a key; a nested object left empty is removed too. Texts are stripped.
    """
    if not isinstance(patch, dict):
        return patch.strip() if isinstance(patch, str) else patch
    merged: JsonObject = dict(target) if isinstance(target, dict) else {}
    for raw_key, value in patch.items():
        key: str = get_local_name(raw_key)
        if value is None or (isinstance(value, str) and not value.strip()):
            merged.pop(key, None)
            continue
        merged[key] = _merge_patch(merged.get(key), _to_local_names(value))
        if merged[key] == {}:
            del merged[key]
    return merged
