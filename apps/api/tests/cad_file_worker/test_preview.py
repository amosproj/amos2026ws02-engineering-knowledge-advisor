import multiprocessing
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from step_documents import DocumentBuilder, box
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkIOImage import vtkPNGReader

from cad_file_worker import preview
from cad_file_worker.errors import StopRequested
from cad_file_worker.preview import create_preview
from services.cad.errors import PreviewError
from services.cad.glb_generator import GlbGenerator
from services.cad.step_parser import StepParser

TIMEOUT: int = 60


def _crash(*_: object) -> None:
    os._exit(3)


def _hang(*_: object) -> None:
    time.sleep(TIMEOUT)


@pytest.fixture(autouse=True)
def no_child_left():
    yield
    assert multiprocessing.active_children() == []


def render(
    glb_path: Path, timeout: float = TIMEOUT, stopping: threading.Event | None = None
) -> Path:
    png_path: Path = glb_path.with_suffix(".png")
    create_preview(
        glb_path, png_path, timeout, stopping or threading.Event(), lambda: None
    )
    return png_path


def test_the_part_is_rendered_on_a_transparent_background(tmp_path: Path):
    builder = DocumentBuilder()
    builder.part("Plate", box())
    step_path: Path = builder.write_step(tmp_path / "plate.step")
    glb_path: Path = tmp_path / "plate.glb"
    GlbGenerator().generate(StepParser().parse(step_path), glb_path)

    reader = vtkPNGReader()
    reader.SetFileName(str(render(glb_path)))
    reader.Update()

    assert reader.GetOutput().GetDimensions() == (512, 384, 1)
    pixels = vtk_to_numpy(reader.GetOutput().GetPointData().GetScalars())
    alpha = pixels[:, 3].reshape(384, 512)
    assert alpha[192, 256] == 255
    assert pixels.reshape(384, 512, 4)[192, 256, :3].max() > 50
    assert not any(
        edge.any() for edge in (alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1])
    )


def test_a_file_without_geometry_raises(tmp_path: Path):
    glb_path: Path = tmp_path / "any.glb"
    glb_path.write_bytes(b"not a GLB")
    with pytest.raises(PreviewError, match="exit code 1"):
        render(glb_path)


@pytest.mark.parametrize(
    ("target", "message"), [(_crash, "exit code 3"), (_hang, "longer than 1 s")]
)
def test_a_crashing_or_hanging_child_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: Callable[..., None],
    message: str,
):
    monkeypatch.setattr(preview, "_render", target)
    with pytest.raises(PreviewError, match=message):
        render(tmp_path / "any.glb", timeout=1 if target is _hang else TIMEOUT)


def test_a_stop_is_not_a_preview_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(preview, "_render", _hang)
    stopping = threading.Event()
    stopping.set()
    with pytest.raises(StopRequested):
        render(tmp_path / "any.glb", stopping=stopping)
