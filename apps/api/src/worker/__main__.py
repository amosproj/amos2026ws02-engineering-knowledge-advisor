"""Background worker for long jobs on uploaded CAD files.

No job runs yet: the checks of uploaded STEP files and the cleanup of abandoned uploads come back with the new data model.
Run with `python -m worker`. See the "Background jobs" section of the api/README.
"""

import logging
import signal
import sys
import time
from pathlib import Path

from logger import logger

POLL_SECONDS = 2

HEARTBEAT_FILE = Path("/tmp/worker-heartbeat")
HEARTBEAT_INTERVAL_SECONDS = 10


class Heartbeat:
    """Touch a file regularly so the container healthcheck can tell the loop is alive."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._last = 0.0

    def beat(self) -> None:
        now = time.monotonic()
        if now - self._last >= HEARTBEAT_INTERVAL_SECONDS:
            self._path.touch()
            self._last = now


def run() -> None:
    heartbeat = Heartbeat(HEARTBEAT_FILE)
    while True:
        heartbeat.beat()
        time.sleep(POLL_SECONDS)


def _exit(*_: object) -> None:
    sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, _exit)
    logger.info("Worker started")
    run()
