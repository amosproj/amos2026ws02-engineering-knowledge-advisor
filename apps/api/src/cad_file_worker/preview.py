import threading
from collections.abc import Callable
from pathlib import Path

from cad_file_worker.child_process import run_in_child
from cad_file_worker.errors import ChildTimeoutError
from services.cad.errors import PreviewError


def create_preview(
    glb_path: Path,
    png_path: Path,
    timeout: float,
    stopping: threading.Event,
    on_progress: Callable[[], None],
) -> None:
    """Renders the GLB to ``png_path``.

    Raises:
        PreviewError: the rendering failed, crashed or took longer than ``timeout`` seconds.
        StopRequested: ``stopping`` was set before the rendering finished.
    """
    try:
        exitcode: int | None = run_in_child(
            _render, (glb_path, png_path), timeout, stopping, on_progress
        )
    except ChildTimeoutError as error:
        raise PreviewError(f"Rendering {error}") from error
    if exitcode != 0:
        raise PreviewError(f"Rendering stopped with exit code {exitcode}")


def _render(glb_path: Path, png_path: Path) -> None:
    # VTK is loaded in the child only
    from services.cad.preview_renderer import render_preview

    render_preview(glb_path, png_path)
