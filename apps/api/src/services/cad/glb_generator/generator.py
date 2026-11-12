from pathlib import Path

from services.cad.model import CadModel


class GlbGenerator:
    """Writes the GLB scene of a ``CadModel``, built from its XDE ``document``.

    Each occurrence node will carry its ``occurrenceId`` in ``extras``.
    """

    def generate(self, model: CadModel, output: Path) -> None:
        print(f"GLB generation not implemented yet: {model.source_name} -> {output}")
