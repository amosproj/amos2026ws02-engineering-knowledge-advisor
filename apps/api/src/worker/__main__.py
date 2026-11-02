"""Background worker: checks uploaded STEP files and cleans up abandoned imports.

This will be also used to process other background jobs in the future, such as extracting the Tree structure from the STEP file.
Run with `python -m worker`. See the "Background jobs" section of the api/REAMDE.
"""

import logging
import signal
import sys
import time
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.exc import SQLAlchemyError

from logger import logger
from worker.cleanup import delete_orphan_objects, expire_abandoned_uploads
from worker.processing import process_next_machine

PROCESSING_POLL_SECONDS = 2
RETRY_PAUSE_SECONDS = 30
CLEANUP_INTERVAL_SECONDS = 60 * 60

HEARTBEAT_FILE = Path("/tmp/worker-heartbeat")
HEARTBEAT_INTERVAL_SECONDS = 10

TRANSIENT_ERRORS = (BotoCoreError, ClientError, SQLAlchemyError, OSError)


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
    next_cleanup = 0.0
    while True:
        heartbeat.beat()

        if time.monotonic() >= next_cleanup:
            _run_cleanup(heartbeat)
            next_cleanup = time.monotonic() + CLEANUP_INTERVAL_SECONDS

        try:
            processed = process_next_machine(heartbeat.beat)
        except TRANSIENT_ERRORS:
            logger.exception(f"Processing failed, retrying in {RETRY_PAUSE_SECONDS} s")
            time.sleep(RETRY_PAUSE_SECONDS)
            continue
        if not processed:
            time.sleep(PROCESSING_POLL_SECONDS)


def _run_cleanup(heartbeat: Heartbeat) -> None:
    try:
        expire_abandoned_uploads()
        delete_orphan_objects(heartbeat.beat)
    except TRANSIENT_ERRORS:
        logger.exception("Cleanup failed, retrying at the next interval")


def _exit(*_: object) -> None:
    sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, _exit)
    logger.info("Worker started")
    run()
