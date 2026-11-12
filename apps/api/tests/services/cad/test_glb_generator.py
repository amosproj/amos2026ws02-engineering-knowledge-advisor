from pathlib import Path

import pytest

from services.cad.glb_generator import GlbGenerator
from services.cad.model import CadModel


def test_generate_only_reports_it_is_not_implemented(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    output: Path = tmp_path / "model.glb"
    GlbGenerator().generate(CadModel("RC-01.step", {}, []), output)

    assert capsys.readouterr().out == (
        f"GLB generation not implemented yet: RC-01.step -> {output}\n"
    )
    assert not output.exists()
