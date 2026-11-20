from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from OCP.TDF import TDF_Label
from step_documents import DocumentBuilder, box, point

from services.cad.errors import GlbGenerationError
from services.cad.glb_generator import GlbGenerator, generator
from services.cad.glb_generator.glb_file import read_glb, write_glb
from services.cad.model import CadModel, CadOccurrence
from services.cad.step_parser import StepParser

type Node = dict[str, Any]


def parse(builder: DocumentBuilder, tmp_path: Path) -> CadModel:
    return StepParser().parse(builder.write_step(tmp_path / "model.step"))


def generate(model: CadModel, tmp_path: Path) -> dict[str, Any]:
    output: Path = tmp_path / "model.glb"
    GlbGenerator().generate(model, output)
    return read_glb(output)[0]


def walk(gltf: dict[str, Any]) -> Iterator[tuple[Node, Node | None]]:
    """Every node with its parent, from the scene's roots."""
    pending: list[tuple[int, Node | None]] = [
        (index, None) for index in gltf["scenes"][0]["nodes"]
    ]
    while pending:
        index, parent = pending.pop()
        node: Node = gltf["nodes"][index]
        yield node, parent
        pending += [(child, node) for child in node.get("children", [])]


def occurrence_nodes(gltf: dict[str, Any]) -> dict[str, Node]:
    return {
        node["extras"]["occurrenceId"]: node
        for node, _ in walk(gltf)
        if "extras" in node
    }


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

    gltf: dict[str, Any] = generate(model, tmp_path)

    links: set[tuple[str, str | None]] = {
        (
            node["extras"]["occurrenceId"],
            None if parent is None else parent["extras"]["occurrenceId"],
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

    gltf: dict[str, Any] = generate(model, tmp_path)

    screws: list[Node] = [
        node for node in occurrence_nodes(gltf).values() if node["name"] == "Screw"
    ]
    assert len(screws) == 3
    assert len({node["extras"]["occurrenceId"] for node in screws}) == 3
    # the writer repeats the mesh entry, but its geometry is stored once
    positions: set[int] = {
        primitive["attributes"]["POSITION"]
        for node in screws
        for primitive in gltf["meshes"][node["mesh"]]["primitives"]
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

    gltf: dict[str, Any] = generate(model, tmp_path)

    assert set(occurrence_nodes(gltf)) == {occ.id for occ in model.occurrences}
    assert "Markers" in [occ.name for occ in model.occurrences]
    nodes: list[Node] = [node for node, _ in walk(gltf)]
    assert all("mesh" not in node for node in nodes if node["name"] == "Marker")
    assert all(
        primitive.get("mode", 4) == 4
        for node in nodes
        if "mesh" in node
        for primitive in gltf["meshes"][node["mesh"]]["primitives"]
    )


def test_parts_without_color_get_a_matte_material(tmp_path: Path):
    gltf: dict[str, Any] = generate(parse(gripper(), tmp_path), tmp_path)

    for node, _ in walk(gltf):
        for primitive in (
            gltf["meshes"][node["mesh"]]["primitives"] if "mesh" in node else []
        ):
            material: dict[str, Any] = gltf["materials"][primitive["material"]]
            assert material["pbrMetallicRoughness"]["metallicFactor"] == 0


def test_non_ascii_names_survive(tmp_path: Path):
    builder = DocumentBuilder()
    builder.part("Stückliste Ø6", box())

    gltf: dict[str, Any] = generate(parse(builder, tmp_path), tmp_path)

    assert [node["name"] for node, _ in walk(gltf)] == ["Stückliste Ø6"]


def test_geometry_is_in_meters(tmp_path: Path):
    builder = DocumentBuilder()
    builder.part("Plate", box(10))

    gltf: dict[str, Any] = generate(parse(builder, tmp_path), tmp_path)

    (mesh,) = gltf["meshes"]
    (primitive,) = mesh["primitives"]
    accessor: dict[str, Any] = gltf["accessors"][primitive["attributes"]["POSITION"]]
    for low, high in zip(accessor["min"], accessor["max"], strict=True):
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
    gltf: dict[str, Any] = {
        "scenes": [{"nodes": [0]}],
        "nodes": [
            {"name": "Line1\nLine2 [0:1:1:1]", "children": [1]},
            {"name": "Plate [1] [0:1:1:1:1]"},
        ],
    }

    generator._set_ids(gltf, occurrences)  # pyright: ignore[reportPrivateUsage]

    assert [node.get("extras", {}).get("occurrenceId") for node in gltf["nodes"]] == [
        "0:1:1:1",
        "0:1:1:1/0:1:1:1:1",
    ]


def test_an_occurrence_without_a_node_raises():
    occurrences: list[CadOccurrence] = [
        CadOccurrence("0:1:1:1", "0:1:1:1", None, "Cell", None),
        CadOccurrence("0:1:1:1/0:1:1:1:1", "0:1:1:2", "0:1:1:1", "Plate", None),
    ]
    gltf: dict[str, Any] = {
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "Cell [0:1:1:1]"}],
    }

    with pytest.raises(GlbGenerationError):
        generator._set_ids(gltf, occurrences)  # pyright: ignore[reportPrivateUsage]


def test_rewriting_the_json_keeps_the_binary_chunk(tmp_path: Path):
    output: Path = tmp_path / "model.glb"
    GlbGenerator().generate(parse(gripper(), tmp_path), output)
    original: bytes = output.read_bytes()

    gltf, rest = read_glb(output)
    write_glb(output, gltf, rest)

    assert output.read_bytes() == original
