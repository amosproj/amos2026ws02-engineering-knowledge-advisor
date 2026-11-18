class StepImportError(Exception):
    """The STEP file cannot be imported at all (unreadable, empty, corrupt)."""


class GlbGenerationError(Exception):
    """The GLB scene of a parsed CAD model cannot be written."""
