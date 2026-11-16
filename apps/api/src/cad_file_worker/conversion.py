"""Converts a STEP file in a child process, so a crash or a hang of Open CASCADE cannot take the worker down."""

import multiprocessing
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from multiprocessing.connection import Connection
from pathlib import Path

from cad_file_worker.errors import ConversionTimeoutError, StopRequested
from services.cad.errors import StepImportError
from services.cad.model import CadModel

POLL_SECONDS = 0.5


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


class _Reader(threading.Thread):
    """Receives the child's result, so the child never blocks on a full pipe and the parent never on a partial one."""

    def __init__(self, receiver: Connection) -> None:
        super().__init__(daemon=True)
        self.receiver: Connection = receiver
        self.result: Conversion | _Failure | None = None

    def run(self) -> None:
        try:
            self.result = self.receiver.recv()
        except (EOFError, OSError):
            # the child died before sending all of its result
            pass


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
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_convert, args=(step_path, glb_path, sender))
    process.start()

    sender.close()
    reader = _Reader(receiver)
    reader.start()
    deadline: float = time.monotonic() + timeout
    try:
        while True:
            if stopping.is_set():
                raise StopRequested
            if time.monotonic() > deadline:
                raise ConversionTimeoutError(
                    f"Converting the STEP file took longer than {timeout} s"
                )
            on_progress()
            # done once the result is read and the child has flushed its output and exited
            if reader.is_alive():
                reader.join(POLL_SECONDS)
            elif process.exitcode is None:
                process.join(POLL_SECONDS)
            else:
                break
    finally:
        process.kill()
        process.join()
        # the child is gone, so the reader ends
        reader.join()
        receiver.close()
        exitcode: int | None = process.exitcode
        process.close()
    if reader.result is None:
        raise StepImportError(f"The STEP conversion stopped with exit code {exitcode}")
    if isinstance(reader.result, _Failure):
        raise StepImportError(reader.result.message)
    return reader.result


def _convert(step_path: Path, glb_path: Path, sender: Connection) -> None:
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
    sender.send(result)
    sender.close()
