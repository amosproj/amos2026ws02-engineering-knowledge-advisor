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
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool

from cad.assembly_tree_node import AssemblyTreeNode
from cad.cad_file import CadFile
from cad.cad_file_parser import CadFileParser


class StepFileParser(CadFileParser):
    def parse_file(self, file_identifier: str, path: str | Path) -> CadFile:
        document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
        XCAFApp_Application.GetApplication_s().InitDocument(document)

        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)

        if reader.ReadFile(str(path)) != IFSelect_RetDone:
            raise ValueError(f"STEP-File could not be read: {path}")

        if not reader.Transfer(document):
            raise ValueError(f"STEP-File content could not be transferred: {path}")

        shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())

        roots = Sequence_TDF_Label()
        shape_tool.GetFreeShapes(roots)

        def label_name(label: TDF_Label) -> str | None:
            name_attr = TDataStd_Name()

            if label.FindAttribute(TDataStd_Name.GetID_s(), name_attr):
                return name_attr.Get().ToExtString()

            return None

        def get_dimensions(label: TDF_Label) -> tuple[float, float, float]:
            shape = XCAFDoc_DocumentTool.ShapeTool_s(document.Main()).GetShape_s(label)
            if shape.IsNull():
                raise ValueError("No shape found for label")

            box = Bnd_Box()
            BRepBndLib.Add_s(shape, box)

            if box.IsVoid():
                raise ValueError("No bounding box found for shape")

            xmin, ymin, zmin = box.CornerMin().Coord()
            xmax, ymax, zmax = box.CornerMax().Coord()

            return xmax - xmin, ymax - ymin, zmax - zmin

        def visit(label: TDF_Label, depth: int = 0) -> AssemblyTreeNode:
            name = label_name(label)
            if not name:
                raise ValueError("No name found for label")

            dims = get_dimensions(label)

            if not shape_tool.IsAssembly_s(label):
                return AssemblyTreeNode(identifier=name, kind="part", dimensions=dims)

            children = Sequence_TDF_Label()
            shape_tool.GetComponents_s(label, children, False)

            nodes: list[AssemblyTreeNode] = []

            for index in range(1, children.Length() + 1):
                occurrence = children.Value(index)

                definition = TDF_Label()
                if not shape_tool.GetReferredShape_s(occurrence, definition):
                    definition = occurrence

                occurrence_name = label_name(occurrence) or label_name(definition)
                if not occurrence_name:
                    raise ValueError("No name found for occurrence")

                child_node = visit(definition, depth + 1)
                child_node.identifier = occurrence_name
                nodes.append(child_node)

            return AssemblyTreeNode(
                identifier=name, kind="assembly", dimensions=dims, children=nodes
            )

        return CadFile(
            identifier=file_identifier,
            root_nodes=[
                visit(roots.Value(index)) for index in range(1, roots.Length() + 1)
            ],
        )
