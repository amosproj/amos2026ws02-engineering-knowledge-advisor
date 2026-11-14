from dataclasses import dataclass
from uuid import uuid4

from services import JsonObject
from services.cad.model import BoundingBox, CadDefinition, CadModel, CadOccurrence


@dataclass(frozen=True)
class CadRecords:
    nodes: dict[str, JsonObject]
    """Record nodes by their new id: the assembly groups, then the instances."""

    machine_properties: JsonObject
    """``MachineProperties`` of the model."""


def to_records(model: CadModel, machine_id: str) -> CadRecords:
    """One ``AssemblyGroup`` per definition, one ``AssemblyInstance`` per occurrence.

    Every root is ``rootOf`` the machine. a machine allows one, so the store refuses a model with several.
    """
    group_ids: dict[str, str] = {}
    groups: dict[str, JsonObject] = {}
    for occurrence in model.occurrences:
        if occurrence.definition_id in group_ids:
            continue
        group_id: str = uuid4().hex
        group_ids[occurrence.definition_id] = group_id
        groups[group_id] = _group(model, occurrence, machine_id)

    instance_ids: dict[str, str] = {}
    paths: dict[str, str] = {}
    instances: dict[str, JsonObject] = {}
    for occurrence in model.occurrences:
        name: str = occurrence.instance_name or occurrence.name
        parent_id: str | None = occurrence.parent_id
        path: str = f"{paths[parent_id]}/{name}" if parent_id else name
        instance_id: str = uuid4().hex
        instance_ids[occurrence.id], paths[occurrence.id] = instance_id, path
        instances[instance_id] = {
            "@type": "AssemblyInstance",
            "name": name,
            "instanceOf": group_ids[occurrence.definition_id],
            **(
                {"partOf": instance_ids[parent_id]}
                if parent_id
                else {"rootOf": machine_id}
            ),
            "properties": {"occurrenceId": occurrence.id, "path": path},
        }

    return CadRecords(
        nodes=groups | instances, machine_properties=_sizes(model.bounding_box)
    )


def _group(model: CadModel, occurrence: CadOccurrence, machine_id: str) -> JsonObject:
    definition: CadDefinition = model.definitions[occurrence.definition_id]
    # an unnamed definition takes the name its first occurrence shows
    name: str = definition.name or occurrence.name
    group: JsonObject = {
        "@type": "AssemblyGroup",
        "identifier": name,
        "name": name,
        "definedIn": machine_id,
    }
    if sizes := _sizes(definition.bounding_box):
        group["properties"] = sizes
    return group


def _sizes(box: BoundingBox | None) -> JsonObject:
    if box is None:
        return {}
    size_x, size_y, size_z = box.size
    return {"sizeX": size_x, "sizeY": size_y, "sizeZ": size_z}
