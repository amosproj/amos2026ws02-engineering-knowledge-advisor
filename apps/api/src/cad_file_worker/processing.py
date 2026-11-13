import asyncio
import threading
import time
from collections.abc import Callable, Generator, Iterator
from contextlib import closing

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cad_file_worker.errors import StopRequested
from cad_file_worker.step_file import StepFileScan, scan_step_file
from logger import logger
from services.catalog import CatalogService
from services.uploads import Upload, UploadStore

CHUNK_SIZE = 8 * 1024 * 1024
MAX_PROCESSING_SECONDS = 30 * 60

UPLOAD_NOT_FOUND = "upload_not_found"
INVALID_STEP_FILE = "invalid_step_file"


async def process_next_cad_upload(
    sessions: async_sessionmaker[AsyncSession],
    catalog: CatalogService,
    stopping: threading.Event,
    on_progress: Callable[[], None],
) -> bool:
    """Check the STEP file waiting longest in processing. Returns False when no file is waiting.

    The row stays locked until its new status is committed, so other workers skip it, the API
    refuses to delete it meanwhile, and a crash hands it back to the next run.
    """
    locked_id: str | None = None
    try:
        async with sessions() as session, session.begin():
            upload: Upload | None = await catalog.uploads.lock_next_to_process(session)
            if upload is None:
                return False

            cad_file_id, source_key = upload.file_id, upload.source_key
            locked_id = cad_file_id
            logger.info(f"Processing CAD file {cad_file_id}")
            scan: StepFileScan | None = await asyncio.to_thread(
                _scan, catalog, source_key, stopping, on_progress
            )
            error_code: str | None = await _save_outcome(
                catalog.uploads, session, cad_file_id, scan
            )
    except StopRequested:
        raise
    except Exception:
        if locked_id is not None:
            await _move_to_back(sessions, catalog.uploads, locked_id)
        raise

    if error_code is None:
        logger.info(f"CAD file {cad_file_id} is ready")
    else:
        logger.info(f"CAD file {cad_file_id} failed: {error_code}")
        if error_code != UPLOAD_NOT_FOUND:
            await asyncio.to_thread(catalog.delete_source_folders, [source_key])
    return True


def _scan(
    catalog: CatalogService,
    source_key: str,
    stopping: threading.Event,
    on_progress: Callable[[], None],
) -> StepFileScan | None:
    """Scan the uploaded file, None if it does not exist."""
    chunks: Generator[bytes] | None = catalog.storage.read_object(
        source_key, CHUNK_SIZE
    )
    if chunks is None:
        return None
    # closed also when stopping or timing out, to release the connection
    with closing(chunks):
        return scan_step_file(_watch(chunks, stopping, on_progress))


def _watch(
    chunks: Iterator[bytes], stopping: threading.Event, on_progress: Callable[[], None]
) -> Iterator[bytes]:
    deadline: float = time.monotonic() + MAX_PROCESSING_SECONDS
    for chunk in chunks:
        if stopping.is_set():
            raise StopRequested
        if time.monotonic() > deadline:
            raise TimeoutError("Reading the STEP file took too long")
        on_progress()
        yield chunk


async def _save_outcome(
    uploads: UploadStore,
    session: AsyncSession,
    cad_file_id: str,
    scan: StepFileScan | None,
) -> str | None:
    """Save the outcome of the check and return its error code, None when ready."""
    if scan is None:
        error_code = UPLOAD_NOT_FOUND
    elif not scan.is_valid:
        error_code = INVALID_STEP_FILE
    else:
        await uploads.set_ready(cad_file_id, scan.sha256, session)
        return None

    await uploads.set_failed(cad_file_id, error_code, session)
    return error_code


async def _move_to_back(
    sessions: async_sessionmaker[AsyncSession],
    uploads: UploadStore,
    cad_file_id: str,
) -> None:
    """Move the file to the back of the queue so it does not block the other files."""
    async with sessions() as session, session.begin():
        await uploads.move_to_back(cad_file_id, session)
