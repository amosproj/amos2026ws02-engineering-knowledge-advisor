from __future__ import annotations

from enum import StrEnum


class Lane(StrEnum):
    """The lane a record's facts take (``Ontology.get_lane``). Members are plain strings."""

    FACT = "fact"
    """Searched for as facts."""
    GUIDELINE = "guideline"
    """Checked against as guidelines."""
