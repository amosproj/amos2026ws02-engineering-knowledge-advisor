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

FILE_ID = "M-1"
ASSEMBLY_NAME = "Robot cell"
PART_NAME = "Input tray"
BOX_SIZE_MM: tuple[float, float, float] = (10.0, 20.0, 30.0)
UNNAMED_BOX_SIZE_MM: tuple[float, float, float] = (5.0, 5.0, 5.0)


def set_name(label: TDF_Label, name: str | None) -> None:
    if name is not None:
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(name))


def write_step_file(
    path: Path,
    *parts: tuple[str | None, str | None, tuple[float, float, float]],
) -> None:
    if not parts:
        parts = ((PART_NAME, PART_NAME, BOX_SIZE_MM),)

    document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    XCAFApp_Application.GetApplication_s().InitDocument(document)

    shape_tool: XCAFDoc_ShapeTool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    assembly: TDF_Label = shape_tool.NewShape()
    TDataStd_Name.Set_s(assembly, TCollection_ExtendedString(ASSEMBLY_NAME))

    for def_name, occ_name, size in parts:
        shape = BRepPrimAPI_MakeBox(*size).Shape()
        label: TDF_Label = shape_tool.AddShape(shape, False)
        set_name(label, def_name)

        occurrence: TDF_Label = shape_tool.AddComponent(
            assembly, label, TopLoc_Location()
        )
        set_name(occurrence, occ_name)

    shape_tool.UpdateAssemblies()

    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.Transfer(document, STEPControl_StepModelType.STEPControl_AsIs)
    writer.Write(str(path))


def test_step_is_parsed(tmp_path: Path) -> None:
    path = tmp_path / "test.step"
    write_step_file(path)

    cad_file: CadFile = StepFileParser().parse_file(FILE_ID, path)
    assert cad_file.identifier == FILE_ID

    root = cad_file.root_node
    assert root.identifier == ASSEMBLY_NAME
    assert root.kind == "assembly"

    part = root.children[0]
    assert part.identifier == PART_NAME
    assert part.kind == "part"
    assert part.dimensions == pytest.approx(BOX_SIZE_MM)


def test_unnamed_parts_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "test_unnamed.step"
    write_step_file(
        path,
        (PART_NAME, PART_NAME, BOX_SIZE_MM),
        (None, None, UNNAMED_BOX_SIZE_MM),
    )

    cad_file = StepFileParser().parse_file(FILE_ID, path)
    root = cad_file.root_node
    assert root.identifier == ASSEMBLY_NAME

    assert len(root.children) == 1
    assert root.children[0].identifier == PART_NAME
