from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from step_documents import DocumentBuilder, box, point

from services.cad.errors import GlbGenerationError
from services.cad.glb_generator import GlbGenerator, generator
from services.cad.glb_generator.glb_file import read_glb_json
from services.cad.model import CadModel, CadOccurrence
from services.cad.step_parser import StepParser

type Node = dict[str, Any]


def parse(builder: DocumentBuilder, tmp_path: Path) -> CadModel:
    return StepParser().parse(builder.write_step(tmp_path / "model.step"))


def generate(model: CadModel, tmp_path: Path) -> dict[str, Any]:
    output: Path = tmp_path / "model.glb"
    GlbGenerator().generate(model, output)
    return read_glb_json(output)


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
    cell = builder.assembly("Cell")
    gripper_assembly = builder.assembly("Gripper")
    builder.add(gripper_assembly, builder.part("Plate", box()))
    screw = builder.part("Screw", box(2))
    for index in range(3):
        builder.add(gripper_assembly, screw, (index * 5, 0, 0))
    builder.add(cell, gripper_assembly, (100, 0, 0))
    builder.add(cell, builder.part("Clamp", box(5)))
    return builder


def test_node_tree_mirrors_occurrences(tmp_path: Path):
    model: CadModel = parse(gripper(), tmp_path)

    gltf = generate(model, tmp_path)

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

    gltf = generate(model, tmp_path)

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
    cell = builder.assembly("Cell")
    builder.add(cell, builder.part(None, box()))
    model: CadModel = parse(builder, tmp_path)

    nodes: dict[str, Node] = occurrence_nodes(generate(model, tmp_path))

    assert set(nodes) == {occ.id for occ in model.occurrences}
    assert all(node["name"] for node in nodes.values())


def test_nodes_without_an_occurrence_carry_no_extras(tmp_path: Path):
    builder = DocumentBuilder()
    cell = builder.assembly("Cell")
    builder.add(cell, builder.part("Plate", box()))
    builder.add(cell, builder.part("Marker", point()))
    model: CadModel = parse(builder, tmp_path)

    gltf = generate(model, tmp_path)

    occurrence_ids: set[str] = {occ.id for occ in model.occurrences}
    assert set(occurrence_nodes(gltf)) == occurrence_ids
    assert "Marker" not in [occ.name for occ in model.occurrences]


def test_non_ascii_names_survive(tmp_path: Path):
    builder = DocumentBuilder()
    builder.part("Stückliste Ø6", box())

    gltf = generate(parse(builder, tmp_path), tmp_path)

    assert [node["name"] for node, _ in walk(gltf)] == ["Stückliste Ø6"]


def test_geometry_is_in_meters(tmp_path: Path):
    builder = DocumentBuilder()
    builder.part("Plate", box(10))

    gltf = generate(parse(builder, tmp_path), tmp_path)

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
