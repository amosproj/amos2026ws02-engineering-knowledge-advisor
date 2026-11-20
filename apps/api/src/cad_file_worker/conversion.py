"""Converts a STEP file in a child process, so a crash or a hang of Open CASCADE cannot take the worker down."""

import multiprocessing
import pickle
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from multiprocessing.context import SpawnContext
from pathlib import Path

from cad_file_worker.errors import ConversionTimeoutError, StopRequested
from services.cad.errors import StepImportError
from services.cad.model import CadModel

POLL_SECONDS: float = 0.5
TEMP_RESULT_FILE_NAME: str = "conversion.pickle"


@dataclass(frozen=True)
class Conversion:
    """The parsed model, and how its GLB went.

    Attributes:
        model: the model, ``document=None``.
        glb_error: why no GLB was written, ``None`` when it was.
    """

    model: CadModel
    glb_error: str | None = None


@dataclass(frozen=True)
class _Failure:
    message: str


def convert_step_file(
    step_path: Path,
    glb_path: Path,
    timeout: float,
    stopping: threading.Event,
    on_progress: Callable[[], None],
) -> Conversion:
    """Parses the STEP file and writes its GLB scene to ``glb_path``.

    A GLB failure does not fail the conversion: it comes back in ``Conversion.glb_error``.

    Raises:
        StepImportError: the file cannot be parsed, or the child process died.
        ConversionTimeoutError: the child did not finish within ``timeout`` seconds.
        StopRequested: ``stopping`` was set before the child finished.
    """
    result_path: Path = glb_path.with_name(TEMP_RESULT_FILE_NAME)
    result_path.unlink(missing_ok=True)
    context: SpawnContext = multiprocessing.get_context("spawn")
    process = context.Process(target=_convert, args=(step_path, glb_path, result_path))
    process.start()
    deadline: float = time.monotonic() + timeout
    try:
        try:
            while True:
                if stopping.is_set():
                    raise StopRequested
                if time.monotonic() > deadline:
                    raise ConversionTimeoutError(
                        f"Converting the STEP file took longer than {timeout} s"
                    )
                on_progress()
                if process.exitcode is not None:
                    break
                process.join(POLL_SECONDS)
        finally:
            process.kill()
            process.join()
            exitcode: int | None = process.exitcode
            process.close()
        return _read_result(result_path, exitcode)
    finally:
        result_path.unlink(missing_ok=True)


def _read_result(result_path: Path, exitcode: int | None) -> Conversion:
    if exitcode != 0 or not result_path.exists():
        raise StepImportError(f"The STEP conversion stopped with exit code {exitcode}")
    with result_path.open("rb") as file:
        result: object = pickle.load(file)
    if isinstance(result, _Failure):
        raise StepImportError(result.message)
    if not isinstance(result, Conversion):
        raise StepImportError("The STEP conversion returned no result")
    return result


def _convert(step_path: Path, glb_path: Path, result_path: Path) -> None:
    # Open CASCADE is loaded in the child only
    from services.cad.glb_generator import GlbGenerator
    from services.cad.step_parser import StepParser

    result: Conversion | _Failure
    try:
        model: CadModel = StepParser().parse(step_path)
    except StepImportError as error:
        result = _Failure(str(error))
    else:
        glb_error: str | None = None
        try:
            GlbGenerator().generate(model, glb_path)
        except Exception as error:  # noqa: BLE001 - no GLB failure may fail the import
            # the 3D model is optional: the parent logs why and imports the tree anyway
            glb_error = f"{type(error).__name__}: {error}"
            glb_path.unlink(missing_ok=True)
        # the document cannot be pickled, so document=None
        result = Conversion(replace(model, document=None), glb_error)
    with result_path.open("wb") as file:
        pickle.dump(result, file)
