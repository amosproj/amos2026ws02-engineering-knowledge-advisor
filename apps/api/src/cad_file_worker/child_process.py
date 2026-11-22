import multiprocessing
import threading
import time
from collections.abc import Callable
from multiprocessing.context import SpawnContext

from cad_file_worker.errors import ChildTimeoutError, StopRequested

POLL_SECONDS: float = 0.5


def run_in_child(
    target: Callable[..., None],
    args: tuple[object, ...],
    timeout: float,
    stopping: threading.Event,
    on_progress: Callable[[], None],
) -> int | None:
    """Runs ``target`` in a child process, so a crash or a hang cannot take the worker down. Returns its exit code.

    Raises:
        ChildTimeoutError: the child did not finish within ``timeout`` seconds.
        StopRequested: ``stopping`` was set before the child finished.
    """
    context: SpawnContext = multiprocessing.get_context("spawn")
    process = context.Process(target=target, args=args)
    process.start()
    deadline: float = time.monotonic() + timeout
    try:
        while True:
            if stopping.is_set():
                raise StopRequested
            if time.monotonic() > deadline:
                raise ChildTimeoutError(f"took longer than {timeout} s")
            on_progress()
            if process.exitcode is not None:
                return process.exitcode
            process.join(POLL_SECONDS)
    finally:
        process.kill()
        process.join()
        process.close()
