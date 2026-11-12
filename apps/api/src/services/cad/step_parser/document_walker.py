import re
from dataclasses import dataclass, replace

from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.collections import Sequence_TDF_Label
from OCP.gp import gp_Pnt
from OCP.TDF import TDF_Label
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_LengthUnit, XCAFDoc_ShapeTool

from services.cad.errors import StepImportError
from services.cad.model import (
    BoundingBox,
    CadDefinition,
    CadModel,
    CadOccurrence,
    DefinitionKind,
    ImportWarning,
    Matrix4,
    Vector3,
    WarningCode,
)
from services.cad.xde import count_subshapes, label_entry, label_name

GENERIC_INSTANCE_NAME: re.Pattern[str] = re.compile(r"^(NAUO\d+|=>\[.*\])$")
# XDE names unnamed representation items after their shape type
SHAPE_TYPE_NAMES: frozenset[str] = frozenset(
    {
        "COMPOUND",
        "COMPSOLID",
        "SOLID",
        "SHELL",
        "FACE",
        "WIRE",
        "EDGE",
        "VERTEX",
        "SHAPE",
    }
)
UNNAMED: str = "Unnamed"
# Open CASCADE reads STEP lengths in millimeters by default
DEFAULT_LENGTH_UNIT: float = 0.001
# nanometers: hides floating-point noise
COORDINATE_DIGITS: int = 9


@dataclass(frozen=True)
class _DefinitionInfo:
    definition: CadDefinition
    components: tuple[TDF_Label, ...]
    face_count: int


class DocumentWalker:
    """Walks the XDE document of a STEP file from its free shapes into a ``CadModel``."""

    def __init__(self, document: TDocStd_Document, source_name: str) -> None:
        self.document: TDocStd_Document = document
        self.source_name: str = source_name
        self.shape_tool: XCAFDoc_ShapeTool = XCAFDoc_DocumentTool.ShapeTool_s(
            document.Main()
        )
        self.unit: float = self._length_unit()
        self.infos: dict[str, _DefinitionInfo] = {}
        self.definitions: dict[str, CadDefinition] = {}
        self.occurrences: list[CadOccurrence] = []
        self.warnings: list[ImportWarning] = []
        self.warned: set[tuple[WarningCode, str]] = set()

    def walk(self) -> CadModel:
        self._check_cycles()
        roots = Sequence_TDF_Label()
        self.shape_tool.GetFreeShapes(roots)
        for index in range(1, roots.Length() + 1):
            self._visit(roots.Value(index), None, TopLoc_Location())
        if not any(
            definition.kind is DefinitionKind.PART
            for definition in self.definitions.values()
        ):
            raise StepImportError(
                f"No visible shapes found in STEP file: {self.source_name}"
            )
        return CadModel(
            source_name=self.source_name,
            definitions=self.definitions,
            occurrences=self.occurrences,
            warnings=self.warnings,
            source_length_unit=self.unit,
            document=self.document,
        )

    def _length_unit(self) -> float:
        root: TDF_Label = self.document.Main().Root()
        attribute = XCAFDoc_LengthUnit()
        if root.IsAttribute(XCAFDoc_LengthUnit.GetID_s()) and root.FindAttribute(
            XCAFDoc_LengthUnit.GetID_s(), attribute
        ):
            return attribute.GetUnitValue()
        return DEFAULT_LENGTH_UNIT

    def _resolve(self, label: TDF_Label) -> TDF_Label | None:
        if not self.shape_tool.IsReference_s(label):
            return label
        definition = TDF_Label()
        if self.shape_tool.GetReferredShape_s(label, definition):
            return definition
        return None

    def _is_placeholder(self, label: TDF_Label) -> bool:
        definition: TDF_Label | None = self._resolve(label)
        return (
            definition is not None
            and not self.shape_tool.IsAssembly_s(definition)
            and label_name(definition) in SHAPE_TYPE_NAMES
        )

    def _components(self, definition: TDF_Label) -> tuple[TDF_Label, ...]:
        if not self.shape_tool.IsAssembly_s(definition):
            return ()
        sequence = Sequence_TDF_Label()
        self.shape_tool.GetComponents_s(definition, sequence, False)
        return tuple(sequence.Value(index) for index in range(1, sequence.Length() + 1))

    def _check_cycles(self) -> None:
        # cycles can have no free root, so check all definitions before walking
        labels = Sequence_TDF_Label()
        self.shape_tool.GetShapes(labels)
        completed: set[str] = set()
        active: set[str] = set()
        for index in range(1, labels.Length() + 1):
            pending: list[tuple[TDF_Label, bool]] = [(labels.Value(index), False)]
            while pending:
                label, leaving = pending.pop()
                definition: TDF_Label | None = self._resolve(label)
                if definition is None:
                    continue
                entry: str = label_entry(definition)
                if leaving:
                    active.remove(entry)
                    completed.add(entry)
                elif entry in active:
                    raise StepImportError(f"Cyclic assembly reference: {entry}")
                elif entry not in completed:
                    active.add(entry)
                    pending.append((definition, True))
                    pending.extend(
                        (child, False) for child in self._components(definition)
                    )

    def _info(self, definition: TDF_Label) -> _DefinitionInfo:
        definition_id: str = label_entry(definition)
        if definition_id in self.infos:
            return self.infos[definition_id]
        components: tuple[TDF_Label, ...] = self._components(definition)
        if components and all(self._is_placeholder(comp) for comp in components):
            components = ()

        shape = self.shape_tool.GetShape_s(definition)
        face_count: int = count_subshapes(shape, TopAbs_FACE)
        info = _DefinitionInfo(
            definition=CadDefinition(
                id=definition_id,
                name=label_name(definition),
                kind=DefinitionKind.ASSEMBLY if components else DefinitionKind.PART,
                solid_count=count_subshapes(shape, TopAbs_SOLID),
                bounding_box=self._definition_box(definition, components, face_count),
            ),
            components=components,
            face_count=face_count,
        )
        self.infos[definition_id] = info
        return info

    def _definition_box(
        self,
        definition: TDF_Label,
        components: tuple[TDF_Label, ...],
        face_count: int,
    ) -> BoundingBox | None:
        """Box in the definition's own coordinates. ``None`` for a dropped part.

        An assembly's is the union of its children's boxes placed by their location, so it can be slightly larger
        than the geometry when a child is rotated by an angle that is not a multiple of 90°.
        """
        if not components:
            if face_count == 0:
                return None
            return self._bounding_box(definition, TopLoc_Location())
        box: BoundingBox | None = None
        for component in components:
            child: TDF_Label | None = self._resolve(component)
            if child is None:
                continue
            child_box: BoundingBox | None = self._info(child).definition.bounding_box
            if child_box is None:
                continue
            placed: BoundingBox = self._place_box(
                child_box, XCAFDoc_ShapeTool.GetLocation_s(component)
            )
            box = placed if box is None else box.union(placed)
        return box

    def _place_box(self, box: BoundingBox, location: TopLoc_Location) -> BoundingBox:
        transform = location.Transformation()
        corners: list[Vector3] = []
        for x in (box.min[0], box.max[0]):
            for y in (box.min[1], box.max[1]):
                for z in (box.min[2], box.max[2]):
                    point = gp_Pnt(x / self.unit, y / self.unit, z / self.unit)
                    point.Transform(transform)
                    corners.append(self._meters(point))
        return BoundingBox(
            min=(
                min(c[0] for c in corners),
                min(c[1] for c in corners),
                min(c[2] for c in corners),
            ),
            max=(
                max(c[0] for c in corners),
                max(c[1] for c in corners),
                max(c[2] for c in corners),
            ),
        )

    def _warn_once(self, code: WarningCode, key: str, warning: ImportWarning) -> None:
        if (code, key) not in self.warned:
            self.warned.add((code, key))
            self.warnings.append(warning)

    def _visit(
        self,
        label: TDF_Label,
        parent_id: str | None,
        parent_location: TopLoc_Location,
    ) -> BoundingBox | None:
        entry: str = label_entry(label)
        occurrence_id: str = f"{parent_id}/{entry}" if parent_id else entry
        definition_label: TDF_Label | None = self._resolve_occurrence(
            label, occurrence_id
        )
        if definition_label is None:
            return None

        info: _DefinitionInfo = self._info(definition_label)
        definition: CadDefinition = info.definition
        instance_name: str = label_name(label)
        if GENERIC_INSTANCE_NAME.match(instance_name):
            instance_name = ""
        name: str = definition.name or instance_name

        if not self._keep_part(info, name):
            return None
        name = self._display_name(name, occurrence_id)

        local_location: TopLoc_Location = XCAFDoc_ShapeTool.GetLocation_s(label)
        world_location: TopLoc_Location = parent_location.Multiplied(local_location)
        index: int = len(self.occurrences)
        self.occurrences.append(
            self._occurrence(
                occurrence_id,
                parent_id,
                definition.id,
                name,
                instance_name,
                local_location,
            )
        )
        self.definitions[definition.id] = definition

        box: BoundingBox | None
        if definition.kind is DefinitionKind.PART:
            box = self._bounding_box(definition_label, world_location)
        else:
            box = self._children_box(info, occurrence_id, world_location)

        self.occurrences[index] = replace(
            self.occurrences[index], world_bounding_box=box
        )
        return box

    def _resolve_occurrence(
        self, label: TDF_Label, occurrence_id: str
    ) -> TDF_Label | None:
        definition: TDF_Label | None = self._resolve(label)
        if definition is None:
            self.warnings.append(
                ImportWarning(
                    WarningCode.UNRESOLVED_REFERENCE,
                    f"Skipped component whose reference cannot be resolved: {occurrence_id}",
                    occurrence_id=occurrence_id,
                )
            )
        return definition

    def _keep_part(self, info: _DefinitionInfo, name: str) -> bool:
        definition: CadDefinition = info.definition
        if definition.kind is DefinitionKind.ASSEMBLY:
            return True
        if info.face_count == 0:
            self._warn_once(
                WarningCode.NO_VISIBLE_GEOMETRY,
                definition.id,
                ImportWarning(
                    WarningCode.NO_VISIBLE_GEOMETRY,
                    f"Dropped part without faces: {name or definition.id}",
                    definition_id=definition.id,
                ),
            )
            return False
        if definition.solid_count > 1:
            self._warn_once(
                WarningCode.MULTIPLE_SOLIDS,
                definition.id,
                ImportWarning(
                    WarningCode.MULTIPLE_SOLIDS,
                    f"Part {name!r} has {definition.solid_count} solids; kept as one part",
                    definition_id=definition.id,
                ),
            )
        return True

    def _display_name(self, name: str, occurrence_id: str) -> str:
        if name:
            return name
        self.warnings.append(
            ImportWarning(
                WarningCode.MISSING_NAME,
                f"Occurrence has no name: {occurrence_id}",
                occurrence_id=occurrence_id,
            )
        )
        return UNNAMED

    def _occurrence(
        self,
        occurrence_id: str,
        parent_id: str | None,
        definition_id: str,
        name: str,
        instance_name: str,
        location: TopLoc_Location,
    ) -> CadOccurrence:
        return CadOccurrence(
            id=occurrence_id,
            definition_id=definition_id,
            parent_id=parent_id,
            name=name,
            instance_name=instance_name
            if instance_name and instance_name != name
            else None,
            local_transform=self._matrix(location),
            world_bounding_box=None,
        )

    def _children_box(
        self,
        info: _DefinitionInfo,
        occurrence_id: str,
        world_location: TopLoc_Location,
    ) -> BoundingBox | None:
        box: BoundingBox | None = None
        for component in info.components:
            child_box: BoundingBox | None = self._visit(
                component, occurrence_id, world_location
            )
            if child_box is not None:
                box = child_box if box is None else box.union(child_box)
        return box

    def _matrix(self, location: TopLoc_Location) -> Matrix4:
        transform = location.Transformation()
        rows: list[tuple[float, float, float, float]] = []
        for row in range(1, 4):
            rows.append(
                (
                    _round(transform.Value(row, 1)),
                    _round(transform.Value(row, 2)),
                    _round(transform.Value(row, 3)),
                    _round(transform.Value(row, 4) * self.unit),
                )
            )
        rows.append((0.0, 0.0, 0.0, 1.0))
        return tuple(rows)

    def _meters(self, point: gp_Pnt) -> Vector3:
        return (
            _round(point.X() * self.unit),
            _round(point.Y() * self.unit),
            _round(point.Z() * self.unit),
        )

    def _bounding_box(
        self, definition: TDF_Label, world: TopLoc_Location
    ) -> BoundingBox | None:
        shape = self.shape_tool.GetShape_s(definition)
        shape = shape.Located(TopLoc_Location()).Moved(world)
        box = Bnd_Box()
        # Add_s bounds surfaces by their control points, which can be meters off for swept surfaces
        BRepBndLib.AddOptimal_s(shape, box, False, False)
        if box.IsVoid():
            return None
        return BoundingBox(
            min=self._meters(box.CornerMin()), max=self._meters(box.CornerMax())
        )


def _round(value: float) -> float:
    # adding 0.0 turns -0.0 into 0.0
    return round(value, COORDINATE_DIGITS) + 0.0
