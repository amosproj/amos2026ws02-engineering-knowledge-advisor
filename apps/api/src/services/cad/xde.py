from OCP.TCollection import TCollection_AsciiString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_Tool
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS_Shape
from OCP.XCAFDoc import XCAFDoc_LengthUnit

# Open CASCADE reads STEP lengths in millimeters by default
DEFAULT_LENGTH_UNIT: float = 0.001


def label_entry(label: TDF_Label) -> str:
    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    return entry.ToCString()


def label_name(label: TDF_Label) -> str:
    # FindAttribute crashes in OCP when the attribute is absent
    attribute = TDataStd_Name()
    if label.IsAttribute(TDataStd_Name.GetID_s()) and label.FindAttribute(
        TDataStd_Name.GetID_s(), attribute
    ):
        return attribute.Get().ToExtString().strip()
    return ""


def count_subshapes(shape: TopoDS_Shape, shape_type: TopAbs_ShapeEnum) -> int:
    explorer = TopExp_Explorer(shape, shape_type)
    count: int = 0
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def document_length_unit(document: TDocStd_Document) -> float:
    """Meters per length unit of the document's coordinates."""
    root: TDF_Label = document.Main().Root()
    attribute = XCAFDoc_LengthUnit()
    if root.IsAttribute(XCAFDoc_LengthUnit.GetID_s()) and root.FindAttribute(
        XCAFDoc_LengthUnit.GetID_s(), attribute
    ):
        return attribute.GetUnitValue()
    return DEFAULT_LENGTH_UNIT
