from dataclasses import dataclass, field
from enum import StrEnum

from OCP.TDocStd import TDocStd_Document

type Vector3 = tuple[float, float, float]
type Matrix4 = tuple[tuple[float, float, float, float], ...]


class DefinitionKind(StrEnum):
    ASSEMBLY = "assembly"
    PART = "part"


class WarningCode(StrEnum):
    UNRESOLVED_REFERENCE = "unresolved_reference"
    NO_VISIBLE_GEOMETRY = "no_visible_geometry"
    MULTIPLE_SOLIDS = "multiple_solids"
    MISSING_NAME = "missing_name"


@dataclass(frozen=True)
class BoundingBox:
    min: Vector3
    max: Vector3

    @property
    def size(self) -> Vector3:
        return (
            self.max[0] - self.min[0],
            self.max[1] - self.min[1],
            self.max[2] - self.min[2],
        )

    def union(self, other: "BoundingBox") -> "BoundingBox":
        return BoundingBox(
            min=(
                min(self.min[0], other.min[0]),
                min(self.min[1], other.min[1]),
                min(self.min[2], other.min[2]),
            ),
            max=(
                max(self.max[0], other.max[0]),
                max(self.max[1], other.max[1]),
                max(self.max[2], other.max[2]),
            ),
        )


@dataclass(frozen=True)
class CadDefinition:
    """A reusable part or assembly. several occurrences may share it.

    ``bounding_box`` is in the definition's own coordinates, so it is the same for every occurrence.
    """

    id: str
    name: str
    kind: DefinitionKind
    solid_count: int
    bounding_box: BoundingBox | None


@dataclass(frozen=True)
class CadOccurrence:
    """One placement of a definition in the model.

    The ID is the path of STEP labels from the root, so it is unique within
    one import (but not stable across file revisions)
    """

    id: str
    definition_id: str
    parent_id: str | None
    name: str
    instance_name: str | None
    local_transform: Matrix4
    world_bounding_box: BoundingBox | None


@dataclass(frozen=True)
class ImportWarning:
    code: WarningCode
    message: str
    definition_id: str | None = None
    occurrence_id: str | None = None


@dataclass
class CadModel:
    """Occurrences are in depth-first order: parents before their children."""

    source_name: str
    definitions: dict[str, CadDefinition]
    occurrences: list[CadOccurrence]
    warnings: list[ImportWarning] = field(default_factory=list)
    source_length_unit: float = 0.001
    """Meters per length unit of ``document`` (model values are already in meters)"""

    document: TDocStd_Document | None = field(default=None, repr=False, compare=False)
    """The Open CASCADE XDE document, keptt for geometry export"""

    @property
    def roots(self) -> list[CadOccurrence]:
        return [occ for occ in self.occurrences if occ.parent_id is None]

    def children_of(self, occurrence_id: str) -> list[CadOccurrence]:
        return [occ for occ in self.occurrences if occ.parent_id == occurrence_id]
