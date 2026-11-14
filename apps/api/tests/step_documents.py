import math
from pathlib import Path

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.IFSelect import IFSelect_RetDone
from OCP.Message import Message, Message_Gravity
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_StepModelType
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Compound, TopoDS_Shape
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

# the STEP writer reports every transfer on stdout, keep failures only
for printer in Message.DefaultMessenger_s().Printers():
    printer.SetTraceLevel(Message_Gravity.Message_Fail)


def box(
    size: float = 10.0, origin: tuple[float, float, float] = (0, 0, 0)
) -> TopoDS_Shape:
    return BRepPrimAPI_MakeBox(gp_Pnt(*origin), size, size, size).Shape()


def compound(*shapes: TopoDS_Shape) -> TopoDS_Compound:
    result = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(result)
    for shape in shapes:
        builder.Add(result, shape)
    return result


def point() -> TopoDS_Compound:
    return compound(BRepBuilderAPI_MakeVertex(gp_Pnt(0, 0, 0)).Vertex())


def set_name(label: TDF_Label, name: str) -> None:
    TDataStd_Name.Set_s(label, TCollection_ExtendedString(name, True))


class DocumentBuilder:
    def __init__(self) -> None:
        self.document = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
        self.shape_tool: XCAFDoc_ShapeTool = XCAFDoc_DocumentTool.ShapeTool_s(
            self.document.Main()
        )
        self.shape_tool.SetAutoNaming_s(False)

    def part(self, name: str | None, shape: TopoDS_Shape) -> TDF_Label:
        return self._named(self.shape_tool.AddShape(shape, False), name)

    def assembly(self, name: str | None) -> TDF_Label:
        return self._named(self.shape_tool.NewShape(), name)

    def add(
        self,
        assembly: TDF_Label,
        child: TDF_Label,
        translation: tuple[float, float, float] = (0, 0, 0),
        rotation_z_degrees: float = 0,
    ) -> TDF_Label:
        rotation = gp_Trsf()
        rotation.SetRotation(
            gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.radians(rotation_z_degrees)
        )
        translate = gp_Trsf()
        translate.SetTranslation(gp_Vec(*translation))
        return self.shape_tool.AddComponent(
            assembly, child, TopLoc_Location(translate.Multiplied(rotation))
        )

    def finish(self) -> TDocStd_Document:
        self.shape_tool.UpdateAssemblies()
        return self.document

    def write_step(self, path: Path) -> Path:
        writer = STEPCAFControl_Writer()
        assert writer.Transfer(
            self.finish(), STEPControl_StepModelType.STEPControl_AsIs
        )
        assert writer.Write(str(path)) == IFSelect_RetDone
        return path

    @staticmethod
    def _named(label: TDF_Label, name: str | None) -> TDF_Label:
        if name is not None:
            set_name(label, name)
        return label
