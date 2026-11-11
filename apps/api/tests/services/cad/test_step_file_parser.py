from pathlib import Path

import pytest
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_StepModelType
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

from services.cad.cad_file import CadFile
from services.cad.step_file_parser import StepFileParser

FILE_ID: str = "M-1"
ASSEMBLY_NAME: str = "Robot cell"
PART_NAME: str = "Input tray"
BOX_SIZE_MM: tuple[float, int, float] = (10.0, 20, 30.0)


def set_name(label: TDF_Label, name: str) -> None:
    TDataStd_Name.Set_s(label, TCollection_ExtendedString(name))


def write_step_file(path: Path) -> None:
    document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    XCAFApp_Application.GetApplication_s().InitDocument(document)

    shape_tool: XCAFDoc_ShapeTool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())

    assembly: TDF_Label = shape_tool.NewShape()
    set_name(assembly, ASSEMBLY_NAME)

    part: TDF_Label = shape_tool.AddShape(
        BRepPrimAPI_MakeBox(*BOX_SIZE_MM).Shape(), False
    )
    set_name(part, PART_NAME)
    occurrence: TDF_Label = shape_tool.AddComponent(assembly, part, TopLoc_Location())
    set_name(occurrence, PART_NAME)

    shape_tool.UpdateAssemblies()

    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    assert writer.Transfer(document, STEPControl_StepModelType.STEPControl_AsIs)
    writer.Write(str(path))


def test_step_is_parsed(tmp_path: Path):
    path: Path = tmp_path / "test.step"
    write_step_file(path)

    cad_file: CadFile = StepFileParser().parse_file(FILE_ID, path)
    assert cad_file.identifier == FILE_ID

    [root] = cad_file.root_nodes
    assert (root.identifier, root.kind) == (ASSEMBLY_NAME, "assembly")

    [part] = root.children
    assert (part.identifier, part.kind) == (PART_NAME, "part")

    assert part.dimensions == pytest.approx(BOX_SIZE_MM)
