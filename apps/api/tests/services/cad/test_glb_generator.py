import struct
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
from OCP.TDF import TDF_Label
from step_documents import DocumentBuilder, box, point

from services import JsonObject, JsonValue
from services.cad.errors import GlbGenerationError
from services.cad.glb_generator import GlbGenerator, generator
from services.cad.glb_generator.glb_file import (
    HEADER_SIZE,
    JSON_CHUNK,
    MAGIC,
    VERSION,
    get_int,
    get_ints,
    get_objects,
    get_str,
    read_glb,
    write_glb,
)
from services.cad.model import CadModel, CadOccurrence
from services.cad.step_parser import StepParser

type Node = JsonObject


def parse(builder: DocumentBuilder, tmp_path: Path) -> CadModel:
    return StepParser().parse(builder.write_step(tmp_path / "model.step"))


def generate(model: CadModel, tmp_path: Path) -> JsonObject:
    output: Path = tmp_path / "model.glb"
    GlbGenerator().generate(model, output)
    return read_glb(output)[0]


def get_object(container: Mapping[str, JsonValue], key: str) -> JsonObject:
    value: JsonValue = container.get(key)
    assert isinstance(value, dict), key
    return value


def get_numbers(container: Mapping[str, JsonValue], key: str) -> list[float]:
    value: JsonValue = container.get(key)
    assert isinstance(value, list), key
    numbers: list[float] = [item for item in value if isinstance(item, int | float)]
    assert len(numbers) == len(value), key
    return numbers


def get_occurrence_id(node: Node) -> str:
    return get_str(get_object(node, "extras"), "occurrenceId")


def get_primitives(gltf: JsonObject, node: Node) -> list[JsonObject]:
    mesh_index: int | None = get_int(node, "mesh")
    if mesh_index is None:
        return []
    return get_objects(get_objects(gltf, "meshes")[mesh_index], "primitives")


def walk(gltf: JsonObject) -> Iterator[tuple[Node, Node | None]]:
    """Every node with its parent, from the scene's roots."""
    nodes: list[Node] = get_objects(gltf, "nodes")
    pending: list[tuple[int, Node | None]] = [
        (index, None) for index in get_ints(get_objects(gltf, "scenes")[0], "nodes")
    ]
    while pending:
        index, parent = pending.pop()
        node: Node = nodes[index]
        yield node, parent
        pending += [(child, node) for child in get_ints(node, "children")]


def occurrence_nodes(gltf: JsonObject) -> dict[str, Node]:
    return {get_occurrence_id(node): node for node, _ in walk(gltf) if "extras" in node}


def gripper() -> DocumentBuilder:
    """Cell > Gripper > Plate and a screw placed three times; Cell > Clamp."""
    builder = DocumentBuilder()
    cell: TDF_Label = builder.assembly("Cell")
    gripper_assembly: TDF_Label = builder.assembly("Gripper")
    builder.add(gripper_assembly, builder.part("Plate", box()))
    screw: TDF_Label = builder.part("Screw", box(2))
    for index in range(3):
        builder.add(gripper_assembly, screw, (index * 5, 0, 0))
    builder.add(cell, gripper_assembly, (100, 0, 0))
    builder.add(cell, builder.part("Clamp", box(5)))
    return builder


def test_node_tree_mirrors_occurrences(tmp_path: Path):
    model: CadModel = parse(gripper(), tmp_path)

    gltf: JsonObject = generate(model, tmp_path)

    links: set[tuple[str, str | None]] = {
        (
            get_occurrence_id(node),
            None if parent is None else get_occurrence_id(parent),
        )
        for node, parent in walk(gltf)
    }
    assert links == {(occ.id, occ.parent_id) for occ in model.occurrences}


def test_every_node_has_its_occurrence_id_and_its_name(tmp_path: Path):
    model: CadModel = parse(gripper(), tmp_path)

    nodes: dict[str, Node] = occurrence_nodes(generate(model, tmp_path))

    for occ in model.occurrences:
        assert nodes[occ.id]["extras"] == {"occurrenceId": occ.id}
        assert nodes[occ.id]["name"] == occ.name


def test_repeated_part_shares_its_geometry_with_distinct_occurrence_ids(tmp_path: Path):
    model: CadModel = parse(gripper(), tmp_path)

    gltf: JsonObject = generate(model, tmp_path)

    screws: list[Node] = [
        node for node in occurrence_nodes(gltf).values() if node["name"] == "Screw"
    ]
    assert len(screws) == 3
    assert len({get_occurrence_id(node) for node in screws}) == 3
    # the writer repeats the mesh entry, but its geometry is stored once
    positions: set[int | None] = {
        get_int(get_object(primitive, "attributes"), "POSITION")
        for node in screws
        for primitive in get_primitives(gltf, node)
    }
    assert len(positions) == 1


def test_unnamed_part_keeps_its_node(tmp_path: Path):
    builder = DocumentBuilder()
    cell: TDF_Label = builder.assembly("Cell")
    builder.add(cell, builder.part(None, box()))
    model: CadModel = parse(builder, tmp_path)

    nodes: dict[str, Node] = occurrence_nodes(generate(model, tmp_path))

    assert set(nodes) == {occ.id for occ in model.occurrences}
    assert all(node["name"] for node in nodes.values())


def test_points_lose_their_mesh_and_keep_the_ids_above_them(tmp_path: Path):
    builder = DocumentBuilder()
    cell: TDF_Label = builder.assembly("Cell")
    builder.add(cell, builder.part("Plate", box()))
    marker: TDF_Label = builder.part("Marker", point())
    builder.add(cell, marker)
    markers: TDF_Label = builder.assembly("Markers")
    builder.add(markers, marker)
    builder.add(cell, markers)
    model: CadModel = parse(builder, tmp_path)

    gltf: JsonObject = generate(model, tmp_path)

    assert set(occurrence_nodes(gltf)) == {occ.id for occ in model.occurrences}
    assert "Markers" in [occ.name for occ in model.occurrences]
    nodes: list[Node] = [node for node, _ in walk(gltf)]
    assert all("mesh" not in node for node in nodes if node["name"] == "Marker")
    assert all(
        get_int(primitive, "mode") in (None, 4)
        for node in nodes
        for primitive in get_primitives(gltf, node)
    )


def test_parts_without_color_get_a_matte_material(tmp_path: Path):
    gltf: JsonObject = generate(parse(gripper(), tmp_path), tmp_path)

    materials: list[JsonObject] = get_objects(gltf, "materials")
    for node, _ in walk(gltf):
        for primitive in get_primitives(gltf, node):
            material_index: int | None = get_int(primitive, "material")
            assert material_index is not None
            material: JsonObject = materials[material_index]
            assert get_object(material, "pbrMetallicRoughness")["metallicFactor"] == 0


def test_non_ascii_names_survive(tmp_path: Path):
    builder = DocumentBuilder()
    builder.part("Stückliste Ø6", box())

    gltf: JsonObject = generate(parse(builder, tmp_path), tmp_path)

    assert [node["name"] for node, _ in walk(gltf)] == ["Stückliste Ø6"]


def test_geometry_is_in_meters(tmp_path: Path):
    builder = DocumentBuilder()
    builder.part("Plate", box(10))

    gltf: JsonObject = generate(parse(builder, tmp_path), tmp_path)

    (mesh,) = get_objects(gltf, "meshes")
    (primitive,) = get_objects(mesh, "primitives")
    position: int | None = get_int(get_object(primitive, "attributes"), "POSITION")
    assert position is not None
    accessor: JsonObject = get_objects(gltf, "accessors")[position]
    for low, high in zip(
        get_numbers(accessor, "min"), get_numbers(accessor, "max"), strict=True
    ):
        assert high - low == pytest.approx(0.01)


def test_a_model_without_document_raises(tmp_path: Path):
    model: CadModel = parse(gripper(), tmp_path)
    model.document = None
    with pytest.raises(GlbGenerationError):
        GlbGenerator().generate(model, tmp_path / "model.glb")


def test_a_newline_in_a_name_keeps_the_ids_below_it():
    occurrences: list[CadOccurrence] = [
        CadOccurrence("0:1:1:1", "0:1:1:1", None, "Line1\nLine2", None),
        CadOccurrence("0:1:1:1/0:1:1:1:1", "0:1:1:2", "0:1:1:1", "Plate", None),
    ]
    gltf: JsonObject = {
        "scenes": [{"nodes": [0]}],
        "nodes": [
            {"name": "Line1\nLine2 [0:1:1:1]", "children": [1]},
            {"name": "Plate [1] [0:1:1:1:1]"},
        ],
    }

    generator._set_ids(gltf, occurrences)  # pyright: ignore[reportPrivateUsage]

    assert [get_occurrence_id(node) for node in get_objects(gltf, "nodes")] == [
        "0:1:1:1",
        "0:1:1:1/0:1:1:1:1",
    ]


def test_an_occurrence_without_a_node_raises():
    occurrences: list[CadOccurrence] = [
        CadOccurrence("0:1:1:1", "0:1:1:1", None, "Cell", None),
        CadOccurrence("0:1:1:1/0:1:1:1:1", "0:1:1:2", "0:1:1:1", "Plate", None),
    ]
    gltf: JsonObject = {
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "Cell [0:1:1:1]"}],
    }

    with pytest.raises(GlbGenerationError):
        generator._set_ids(gltf, occurrences)  # pyright: ignore[reportPrivateUsage]


def test_json_chunk_that_is_not_object_raises(tmp_path: Path):
    text: bytes = b"[]  "
    body: bytes = struct.pack("<II", len(text), JSON_CHUNK) + text
    path: Path = tmp_path / "model.glb"
    path.write_bytes(
        MAGIC + struct.pack("<II", VERSION, HEADER_SIZE + len(body)) + body
    )
    with pytest.raises(GlbGenerationError):
        read_glb(path)


@pytest.mark.parametrize(
    "container",
    [{"nodes": 5}, {"nodes": [5]}, {"nodes": [{"children": ["0"]}]}],
    ids=["no list", "no objects", "no integers"],
)
def test_malformed_gltf_raises(container: JsonObject):
    with pytest.raises(GlbGenerationError):
        for node in get_objects(container, "nodes"):
            get_ints(node, "children")


def test_rewriting_the_json_keeps_the_binary_chunk(tmp_path: Path):
    output: Path = tmp_path / "model.glb"
    GlbGenerator().generate(parse(gripper(), tmp_path), output)
    original: bytes = output.read_bytes()

    gltf, rest = read_glb(output)
    write_glb(output, gltf, rest)

    assert output.read_bytes() == original
