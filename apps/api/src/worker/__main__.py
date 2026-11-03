"""Background worker: checks uploaded STEP files and cleans up abandoned uploads and orphan objects.

This will be also used to process other background jobs in the future, such as extracting the Tree structure from the STEP file.
Run with `python -m worker`. See the "Storage and background jobs" section of the api/README.
"""

import asyncio
import logging
import signal
import threading
import time
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.settings import get_settings
from db import create_engine, create_ograg_service, create_sessionmaker
from logger import logger
from services import ConflictError
from services.ograg.service import OgRagService
from worker.cleanup import delete_orphan_objects, expire_abandoned_uploads
from worker.processing import StopRequested, process_next_cad_upload

PROCESSING_POLL_SECONDS = 2
RETRY_PAUSE_SECONDS = 30
CLEANUP_INTERVAL_SECONDS = 60 * 60

HEARTBEAT_FILE = Path("/tmp/worker-heartbeat")
HEARTBEAT_INTERVAL_SECONDS = 10

TRANSIENT_ERRORS = (BotoCoreError, ClientError, SQLAlchemyError, ConflictError, OSError)

# set on SIGTERM; the file scan checks it between chunks, as a thread cannot be cancelled
stopping = threading.Event()


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


async def run() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    sessions = create_sessionmaker(engine)
    ograg = create_ograg_service(settings, engine)
    heartbeat = Heartbeat(HEARTBEAT_FILE)
    next_cleanup = 0.0
    try:
        while not stopping.is_set():
            heartbeat.beat()

            if time.monotonic() >= next_cleanup:
                await _run_cleanup(sessions, ograg, heartbeat)
                next_cleanup = time.monotonic() + CLEANUP_INTERVAL_SECONDS

            try:
                processed = await process_next_cad_upload(
                    sessions, stopping, heartbeat.beat
                )
            except StopRequested:
                break
            except TRANSIENT_ERRORS:
                logger.exception(
                    f"Processing failed, retrying in {RETRY_PAUSE_SECONDS} s"
                )
                await _pause(RETRY_PAUSE_SECONDS)
                continue
            if not processed:
                await _pause(PROCESSING_POLL_SECONDS)
    finally:
        await engine.dispose()
    logger.info("Worker stopped")


async def _run_cleanup(
    sessions: async_sessionmaker[AsyncSession],
    ograg: OgRagService,
    heartbeat: Heartbeat,
) -> None:
    try:
        await expire_abandoned_uploads(sessions, ograg, stopping, heartbeat.beat)
        await delete_orphan_objects(sessions, stopping, heartbeat.beat)
    except TRANSIENT_ERRORS:
        logger.exception("Cleanup failed, retrying at the next interval")


async def _pause(seconds: float) -> None:
    """Sleep, but wake up as soon as the worker is asked to stop."""
    await asyncio.to_thread(stopping.wait, seconds)


def _stop(*_: object) -> None:
    stopping.set()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, _stop)
    logger.info("Worker started")
    asyncio.run(run())
