from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Open CASCADE takes seconds to load, the API only needs the data
    from OCP.TDocStd import TDocStd_Document

type Vector3 = tuple[float, float, float]

# nanometers: hides floating-point noise
LENGTH_DIGITS: int = 9


def round_length(value: float) -> float:
    # adding 0.0 turns -0.0 into 0.0
    return round(value, LENGTH_DIGITS) + 0.0


@dataclass(frozen=True)
class BoundingBox:
    min: Vector3
    max: Vector3

    @property
    def size(self) -> Vector3:
        return (
            round_length(self.max[0] - self.min[0]),
            round_length(self.max[1] - self.min[1]),
            round_length(self.max[2] - self.min[2]),
        )

    def union(self, other: BoundingBox) -> BoundingBox:
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


@dataclass
class CadModel:
    """Occurrences are in depth-first order: parents before their children."""

    source_name: str
    definitions: dict[str, CadDefinition]
    occurrences: list[CadOccurrence]
    bounding_box: BoundingBox | None

    document: TDocStd_Document | None = field(default=None, repr=False, compare=False)
    """The Open CASCADE XDE document, kept for geometry export"""

    @property
    def roots(self) -> list[CadOccurrence]:
        return [occ for occ in self.occurrences if occ.parent_id is None]
