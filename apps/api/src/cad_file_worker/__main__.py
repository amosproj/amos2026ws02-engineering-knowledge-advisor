"""CAD file worker: checks uploaded STEP files and cleans up abandoned uploads and orphan objects.

Run with `python -m cad_file_worker`. See the "Storage and background jobs" section of the api/README.
"""

import asyncio
import logging
import signal
import threading
import time
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from cad_file_worker.cleanup import delete_orphan_objects, expire_abandoned_uploads
from cad_file_worker.errors import StopRequested
from cad_file_worker.processing import process_next_cad_upload
from config.settings import Settings, get_settings
from db.session import (
    create_catalog_service,
    create_engine,
    create_ograg_service,
    create_sessionmaker,
)
from logger import logger
from services import ConflictError
from services.catalog import CatalogService
from services.object_storage import ObjectStorageError

PROCESSING_POLL_SECONDS = 2
RETRY_PAUSE_SECONDS = 30
CLEANUP_INTERVAL_SECONDS = 60 * 60

HEARTBEAT_FILE: Path = Path("/tmp/cad-file-worker-heartbeat")
HEARTBEAT_INTERVAL_SECONDS = 10

TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    ObjectStorageError,
    SQLAlchemyError,
    ConflictError,
    OSError,
)

# set on SIGTERM; the file scan checks it between chunks, as a thread cannot be cancelled
stopping = threading.Event()


class Heartbeat:
    """Touch a file regularly so the container healthcheck can tell the loop is alive."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._last = 0.0

    def beat(self) -> None:
        now: float = time.monotonic()
        if now - self._last >= HEARTBEAT_INTERVAL_SECONDS:
            self._path.touch()
            self._last = now


async def run() -> None:
    settings: Settings = get_settings()
    engine: AsyncEngine = create_engine(settings)
    sessions: async_sessionmaker[AsyncSession] = create_sessionmaker(engine)
    catalog: CatalogService = create_catalog_service(
        settings, create_ograg_service(settings, engine)
    )
    heartbeat: Heartbeat = Heartbeat(HEARTBEAT_FILE)
    next_cleanup = 0.0
    try:
        while not stopping.is_set():
            heartbeat.beat()

            if time.monotonic() >= next_cleanup:
                await _run_cleanup(sessions, catalog, heartbeat)
                next_cleanup = time.monotonic() + CLEANUP_INTERVAL_SECONDS

            try:
                processed: bool = await process_next_cad_upload(
                    sessions, catalog, stopping, heartbeat.beat
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
    logger.info("CAD file worker stopped")


async def _run_cleanup(
    sessions: async_sessionmaker[AsyncSession],
    catalog: CatalogService,
    heartbeat: Heartbeat,
) -> None:
    try:
        await expire_abandoned_uploads(sessions, catalog, stopping, heartbeat.beat)
        await delete_orphan_objects(sessions, catalog, stopping, heartbeat.beat)
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
    logger.info("CAD file worker started")
    asyncio.run(run())
