import re
from pathlib import Path

from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.IFSelect import IFSelect_RetDone
from OCP.OCP.collections import Sequence_TDF_Label  # pyright: ignore
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label
from OCP.TDocStd import TDocStd_Document
from OCP.TopoDS import TopoDS_Shape
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

from services.cad.assembly_tree_node import AssemblyTreeNode
from services.cad.cad_file import CadFile
from services.cad.cad_file_parsing_error import CadFileParsingError
from services.cad_file_parser import CadFileParser

# Matches auto-generated names like "=>[0:0:1:0]" from OpenCASCADE
_AUTO_GENERATED_NAME_RE = re.compile(r"^=>\[.*]")


class StepFileParser(CadFileParser):
    def parse_file(self, file_identifier: str, path: str | Path) -> CadFile:
        document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
        XCAFApp_Application.GetApplication_s().InitDocument(document)

        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)

        if reader.ReadFile(str(path)) != IFSelect_RetDone:
            raise CadFileParsingError(f"STEP-File could not be read: {path}")

        if not reader.Transfer(document):
            raise CadFileParsingError(
                f"STEP-File content could not be transferred: {path}"
            )

        shape_tool: XCAFDoc_ShapeTool = XCAFDoc_DocumentTool.ShapeTool_s(
            document.Main()
        )

        roots = Sequence_TDF_Label()
        shape_tool.GetFreeShapes(roots)

        if len(roots) != 1:
            raise CadFileParsingError(
                f"Expected exactly one root node, but found {len(roots)}"
            )

        def label_name(label: TDF_Label) -> str | None:
            name_attr = TDataStd_Name()
            if label.FindAttribute(TDataStd_Name.GetID_s(), name_attr):
                name = name_attr.Get().ToExtString()
                if not _AUTO_GENERATED_NAME_RE.match(name):
                    return name
            return None

        def get_dimensions(
            label: TDF_Label,
        ) -> tuple[float | int, float | int, float | int]:
            shape: TopoDS_Shape = XCAFDoc_DocumentTool.ShapeTool_s(
                document.Main()
            ).GetShape_s(label)
            if shape.IsNull():
                raise CadFileParsingError("No shape found for label")

            box = Bnd_Box()
            BRepBndLib.Add_s(shape, box)

            if box.IsVoid():
                raise CadFileParsingError("No bounding box found for shape")

            xmin, ymin, zmin = box.CornerMin().Coord()
            xmax, ymax, zmax = box.CornerMax().Coord()

            return xmax - xmin, ymax - ymin, zmax - zmin

        def visit(label: TDF_Label) -> AssemblyTreeNode | None:
            name: str | None = label_name(label)
            if not name:
                return None

            dims: tuple[float | int, float | int, float | int] = get_dimensions(label)

            if not shape_tool.IsAssembly_s(label):
                return AssemblyTreeNode(identifier=name, kind="part", dimensions=dims)

            children = Sequence_TDF_Label()
            shape_tool.GetComponents_s(label, children, False)

            nodes: list[AssemblyTreeNode] = []

            for index in range(1, children.Length() + 1):
                occurrence: TDF_Label = children.Value(index)

                definition = TDF_Label()
                if not shape_tool.GetReferredShape_s(occurrence, definition):
                    definition = occurrence

                child_node: AssemblyTreeNode | None = visit(definition)
                if child_node is None:
                    continue

                occurrence_name: str | None = label_name(occurrence)
                if occurrence_name is None:
                    continue

                child_node.identifier = occurrence_name
                nodes.append(child_node)

            return AssemblyTreeNode(
                identifier=name, kind="assembly", dimensions=dims, children=nodes
            )

        root_node = visit(roots.Value(1))
        if root_node is None:
            raise CadFileParsingError("No name found for root assembly")

        return CadFile(
            identifier=file_identifier,
            root_node=root_node,
        )
