"""Machines, their assembly groups and the CAD files of these groups, stored as records.

Hierarchy: CadFile -partOf-> AssemblyGroup -partOf-> Machine. Every function runs in the caller's
transaction and does not commit: a failure must roll back the whole operation.
"""

from collections.abc import Mapping
from uuid import uuid4

from services import Json, JsonObject, Link, Record, Tx
from services.ograg.ontology import get_local_name, to_list
from services.ograg.service import DeleteResult, OgRagService, RecordError

MACHINE: str = "Machine"
ASSEMBLY_GROUP: str = "AssemblyGroup"
CAD_FILE: str = "CadFile"
PART_OF: str = "partOf"
CAD_FORMAT: str = "STEP"

EDITABLE_FIELDS: dict[str, tuple[str, ...]] = {
    MACHINE: ("name", "description", "customer", "identifier"),
    ASSEMBLY_GROUP: ("name", "description", "identifier"),
    CAD_FILE: ("name",),
}

ERROR_NOT_FOUND: str = "no {cls} {record_id!r}"
ERROR_NAME_REQUIRED: str = "name must not be empty"
ERROR_NOT_EDITABLE: str = "{cls} has no editable field {field!r}"
ERROR_IDENTIFIER_TAKEN: str = (
    "identifier {identifier!r} is already used by {record_id!r}"
)

type Fields = Mapping[str, str | None]


class NotFoundError(LookupError):
    """No record of the expected class has this id."""


class IdentifierTakenError(ValueError):
    """Another record already uses this identifier: another machine, or another group of the same machine."""


async def create_machine(ograg: OgRagService, tx: Tx, fields: Fields) -> str:
    return await _create(ograg, tx, MACHINE, fields, parent_id=None)


async def create_assembly_group(
    ograg: OgRagService, tx: Tx, machine_id: str, fields: Fields
) -> str:
    await get_record(ograg, tx, MACHINE, machine_id)
    return await _create(ograg, tx, ASSEMBLY_GROUP, fields, parent_id=machine_id)


async def create_cad_file(
    ograg: OgRagService, tx: Tx, assembly_group_id: str, name: str
) -> str:
    await get_record(ograg, tx, ASSEMBLY_GROUP, assembly_group_id)
    return await _create(
        ograg, tx, CAD_FILE, {"name": name}, parent_id=assembly_group_id
    )


async def update_record(
    ograg: OgRagService, tx: Tx, cls: str, record_id: str, changes: Fields
) -> None:
    """Changes only the fields given in ``changes``. ``None`` or blank clears an optional field."""
    # the row lock makes concurrent updates of this record wait instead of overwriting each other
    await ograg.store.lock_record(record_id, tx)
    record: Record = await get_record(ograg, tx, cls, record_id)
    # the generic records endpoint also accepts prefixed names such as og:name
    node: JsonObject = {
        get_local_name(key): value for key, value in record.input.items()
    }
    cleaned: dict[str, str | None] = _clean_fields(cls, changes)
    for field, value in cleaned.items():
        if value is None:
            node.pop(field, None)
        else:
            node[field] = value
    _check_name(node)
    identifier: str | None = cleaned.get("identifier")
    if identifier is not None:
        await _check_identifier_free(
            ograg, tx, cls, identifier, record_id, _get_parent_id(record)
        )
    await ograg.upsert_record(record_id, node, tx)


async def delete_machine(ograg: OgRagService, tx: Tx, machine_id: str) -> list[str]:
    """Deletes the machine with its assembly groups and their CAD files. Returns the deleted ids."""
    # locked first, so no group can be added while its groups are listed and deleted
    await ograg.store.lock_record(machine_id, tx)
    await get_record(ograg, tx, MACHINE, machine_id)
    deleted_ids: list[str] = []
    for group in await list_children(ograg, tx, machine_id, ASSEMBLY_GROUP):
        deleted_ids += await delete_assembly_group(ograg, tx, group.id)
    return deleted_ids + await _delete(ograg, tx, machine_id)


async def delete_assembly_group(
    ograg: OgRagService, tx: Tx, assembly_group_id: str
) -> list[str]:
    """Deletes the assembly group with its CAD files. Returns the deleted ids."""
    await ograg.store.lock_record(assembly_group_id, tx)
    await get_record(ograg, tx, ASSEMBLY_GROUP, assembly_group_id)
    deleted_ids: list[str] = []
    for cad_file in await list_children(ograg, tx, assembly_group_id, CAD_FILE):
        deleted_ids += await _delete(ograg, tx, cad_file.id)
    return deleted_ids + await _delete(ograg, tx, assembly_group_id)


async def delete_cad_file(ograg: OgRagService, tx: Tx, cad_file_id: str) -> list[str]:
    await get_record(ograg, tx, CAD_FILE, cad_file_id)
    return await _delete(ograg, tx, cad_file_id)


async def get_record(ograg: OgRagService, tx: Tx, cls: str, record_id: str) -> Record:
    record: Record | None = await ograg.store.get_record(record_id, tx)
    if record is None or record.cls != cls:
        raise NotFoundError(ERROR_NOT_FOUND.format(cls=cls, record_id=record_id))
    return record


async def list_machines(ograg: OgRagService, tx: Tx) -> list[Record]:
    return await ograg.store.get_records_by_class(MACHINE, tx)


async def list_children(
    ograg: OgRagService, tx: Tx, parent_id: str, cls: str
) -> list[Record]:
    """Returns the records of class ``cls`` that are part of ``parent_id``, sorted by id.

    Knowledge items also link to machines and groups, but not through ``partOf``.
    """
    linking: list[Record] = await ograg.store.get_linking_records([parent_id], tx)
    return [
        rec
        for rec in linking
        if rec.cls == cls and Link(PART_OF, parent_id) in rec.links
    ]


async def _create(
    ograg: OgRagService, tx: Tx, cls: str, fields: Fields, parent_id: str | None
) -> str:
    node: JsonObject = {
        field: value
        for field, value in _clean_fields(cls, fields).items()
        if value is not None
    }
    _check_name(node)
    if cls == CAD_FILE:
        node["format"] = CAD_FORMAT
    if parent_id is not None:
        node[PART_OF] = parent_id
    record_id: str = uuid4().hex
    if "identifier" in node:
        await _check_identifier_free(
            ograg, tx, cls, str(node["identifier"]), record_id, parent_id
        )
    await ograg.upsert_record(record_id, {"@type": cls, **node}, tx)
    return record_id


async def _delete(ograg: OgRagService, tx: Tx, record_id: str) -> list[str]:
    # knowledge items that lose their last link are kept and marked for review
    result: DeleteResult = await ograg.delete_record(
        record_id, tx, delete_orphans=False
    )
    return result.deleted_ids


def _clean_fields(cls: str, fields: Fields) -> dict[str, str | None]:
    """Returns ``fields`` stripped, blank values as ``None``.

    Raises:
        RecordError: a field cannot be edited for ``cls``.
    """
    cleaned: dict[str, str | None] = {}
    for field, value in fields.items():
        if field not in EDITABLE_FIELDS[cls]:
            raise RecordError(ERROR_NOT_EDITABLE.format(cls=cls, field=field))
        cleaned[field] = (value or "").strip() or None
    return cleaned


def _check_name(node: Mapping[str, Json]) -> None:
    if not str(node.get("name") or "").strip():
        raise RecordError(ERROR_NAME_REQUIRED)


def _get_parent_id(record: Record) -> str | None:
    return next(
        (link.target_id for link in record.links if link.property_name == PART_OF),
        None,
    )


async def _check_identifier_free(
    ograg: OgRagService,
    tx: Tx,
    cls: str,
    identifier: str,
    record_id: str,
    parent_id: str | None,
) -> None:
    """Machine identifiers are unique among machines, group identifiers within their machine.

    Case and surrounding spaces are ignored.

    Raises:
        IdentifierTakenError: another record uses ``identifier``.
    """
    others: list[Record] = (
        await ograg.store.get_records_by_class(cls, tx)
        if parent_id is None
        else await list_children(ograg, tx, parent_id, cls)
    )
    wanted: str = identifier.strip().casefold()
    for other in others:
        identifiers: list[str] = [
            str(val).strip().casefold()
            for val in to_list(other.graph.get("identifier", []))
        ]
        if other.id != record_id and wanted in identifiers:
            raise IdentifierTakenError(
                ERROR_IDENTIFIER_TAKEN.format(identifier=identifier, record_id=other.id)
            )
