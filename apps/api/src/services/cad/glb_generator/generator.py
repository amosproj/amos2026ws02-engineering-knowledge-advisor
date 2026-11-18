import re
from pathlib import Path
from typing import Any

from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.collections import (
    IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString,
    Sequence_TDF_Label,
)
from OCP.Message import Message_ProgressRange
from OCP.RWGltf import RWGltf_CafWriter
from OCP.RWMesh import RWMesh_CoordinateSystem, RWMesh_NameFormat
from OCP.Standard import Standard_Failure
from OCP.TCollection import TCollection_AsciiString
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

from services.cad.errors import GlbGenerationError
from services.cad.glb_generator.glb_file import read_glb, write_glb
from services.cad.model import CadModel, CadOccurrence
from services.cad.xde import document_length_unit

# Tessellation quality: CAD surfaces are exact curves, a GLB only holds flat triangles,
# so BRepMesh_IncrementalMesh approximates every face with triangles using these two limits.
#
# Smaller values -> smoother curves, but more triangles, which means:
#   - a bigger GLB (larger S3 objects, slower download and browser load)
#   - longer conversion time in the worker
#   - more RAM in the worker; large assemblies already need over 2 GB at these values
# Larger values -> smaller, faster files, but holes and shafts look visibly faceted.
#
# Current values are coarse on purpose ("navigation first": the 3D view is for
# finding and clicking parts, not for inspecting surfaces). Before changing them,
# compare GLB size, conversion time and peak RAM on a large assembly.

# Max distance between triangles and the true surface, as a fraction of each edge's
# size (relative, see the True passed to BRepMesh_IncrementalMesh): 0.01 = 1 %.
# Relative keeps small and large parts at similar visual quality.
LINEAR_DEFLECTION: float = 0.01

# Max angle between neighbouring triangles along a curve, in radians.
# 0.5 rad ≈ 29°, so a full circle gets at least ~13 segments (2π / 0.5).
# Halving it roughly doubles the segments on every curved edge.
ANGULAR_DEFLECTION: float = 0.5

# the writer ends each node name with its label entry, e.g. "Plate [1] [0:1:1:2:1]"
# DOTALL: STEP names may contain line breaks
ENTRY_SUFFIX: re.Pattern[str] = re.compile(
    r"^(.*?)\s*(?:\[[^\]]*\]\s*)*\[([0-9:]+)\]$", re.DOTALL
)
UNNAMED: str = "Unnamed"
# for parts without a color in the STEP file
DEFAULT_GREY: float = 0.7
TRIANGLES: int = 4


class GlbGenerator:
    """Writes the GLB scene of a ``CadModel``, built from its XDE ``document``.

    One node per occurrence, nested like the occurrences, named after it and carrying
    ``{"occurrenceId"}`` in ``extras``. Nodes no occurrence stands for (merged or
    dropped geometry) carry no ``extras``.
    """

    def generate(self, model: CadModel, output: Path) -> None:
        """Writes the GLB to ``output``.

        Raises:
            GlbGenerationError: no GLB could be written.
        """
        if model.document is None:
            raise GlbGenerationError(f"No document to export: {model.source_name}")
        try:
            _write(model.document, output)
            gltf, rest = read_glb(output)
            _set_ids(gltf, model.occurrences)
            _drop_points_and_lines(gltf)
            _make_matte(gltf)
            write_glb(output, gltf, rest)
        except (Standard_Failure, OSError, ValueError) as error:
            raise GlbGenerationError(f"Could not write the GLB: {error}") from error


def _write(document: TDocStd_Document, path: Path) -> None:
    shape_tool: XCAFDoc_ShapeTool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    roots = Sequence_TDF_Label()
    shape_tool.GetFreeShapes(roots)
    for index in range(1, roots.Length() + 1):
        BRepMesh_IncrementalMesh(
            shape_tool.GetShape_s(roots.Value(index)),
            LINEAR_DEFLECTION,
            True,
            ANGULAR_DEFLECTION,
            True,
        )

    writer = RWGltf_CafWriter(TCollection_AsciiString(str(path)), True)
    # one primitive per part instead of one per face
    writer.SetMergeFaces(True)
    writer.SetNodeNameFormat(
        RWMesh_NameFormat.RWMesh_NameFormat_ProductAndInstanceAndOcaf
    )
    converter = writer.ChangeCoordinateSystemConverter()
    # CAD is Z-up in the document's unit, glTF Y-up in meters
    converter.SetInputLengthUnit(document_length_unit(document))
    converter.SetInputCoordinateSystem(
        RWMesh_CoordinateSystem.RWMesh_CoordinateSystem_Zup
    )
    file_info = IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString()
    if not writer.Perform(document, file_info, Message_ProgressRange()):
        raise GlbGenerationError(f"Open CASCADE could not write {path.name}")


def _set_ids(gltf: dict[str, Any], occurrences: list[CadOccurrence]) -> None:
    """Names each node after its occurrence and adds the ids, matched by the path of label entries.

    Raises:
        GlbGenerationError: an occurrence has no node.
    """
    by_id: dict[str, CadOccurrence] = {occ.id: occ for occ in occurrences}
    nodes: list[dict[str, Any]] = gltf.get("nodes", [])
    roots: list[int] = [
        index for scene in gltf.get("scenes", []) for index in scene.get("nodes", [])
    ]
    pending: list[tuple[int, str | None]] = [(index, None) for index in roots]
    while pending:
        index, parent_path = pending.pop()
        node: dict[str, Any] = nodes[index]
        match: re.Match[str] | None = ENTRY_SUFFIX.match(node.get("name", ""))
        product: str = match.group(1) if match else node.get("name", "")
        path: str | None = None
        if match:
            entry: str = match.group(2)
            path = f"{parent_path}/{entry}" if parent_path else entry
        occurrence: CadOccurrence | None = by_id.get(path) if path else None
        if occurrence is not None:
            node["name"] = occurrence.name
            node["extras"] = {"occurrenceId": occurrence.id}
            del by_id[occurrence.id]
        else:
            node["name"] = product or UNNAMED
            node.pop("extras", None)
        pending += [(child, path) for child in node.get("children", [])]
    if by_id:
        raise GlbGenerationError(
            f"{len(by_id)} occurrences have no glTF node, e.g. {next(iter(by_id))}"
        )


def _drop_points_and_lines(gltf: dict[str, Any]) -> None:
    """Unlinks the meshes of free vertices and edges: invisible, but viewers pick them and select the wrong part."""
    meshes: list[dict[str, Any]] = gltf.get("meshes", [])
    for node in gltf.get("nodes", []):
        if "mesh" in node and not any(
            primitive.get("mode", TRIANGLES) == TRIANGLES
            for primitive in meshes[node["mesh"]]["primitives"]
        ):
            del node["mesh"]


def _make_matte(gltf: dict[str, Any]) -> None:
    """glTF defaults to fully metallic, which renders almost black without an environment map.

    Primitives without a material (parts without a color) get a grey one.
    """
    materials: list[dict[str, Any]] = gltf.setdefault("materials", [])
    for material in materials:
        material.setdefault("pbrMetallicRoughness", {}).setdefault(
            "metallicFactor", 0.0
        )
    uncolored: list[dict[str, Any]] = [
        primitive
        for mesh in gltf.get("meshes", [])
        for primitive in mesh["primitives"]
        if "material" not in primitive
    ]
    if uncolored:
        materials.append(
            {
                "name": "default",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [DEFAULT_GREY, DEFAULT_GREY, DEFAULT_GREY, 1.0],
                    "metallicFactor": 0.0,
                },
            }
        )
        for primitive in uncolored:
            primitive["material"] = len(materials) - 1
