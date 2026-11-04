import asyncio
import threading
import time
from collections.abc import Callable, Generator, Iterator
from contextlib import closing

from psycopg import errors as pg_errors
from sqlalchemy import Row, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cad_file_worker.step_file import StepFileScan, scan_step_file
from db import CadUploadColumn, CadUploadStatus, cad_uploads
from db.cad_uploads import SHA256_READY_INDEX
from logger import logger
from services.catalog import CatalogService

CHUNK_SIZE = 8 * 1024 * 1024
MAX_PROCESSING_SECONDS = 30 * 60

UPLOAD_NOT_FOUND = "upload_not_found"
INVALID_STEP_FILE = "invalid_step_file"
DUPLICATE_FILE = "duplicate_file"


class StopRequested(Exception):
    """The worker is shutting down: the file is left in processing for the next start."""


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
            upload: Row[str, str] | None = (
                await session.execute(
                    select(
                        cad_uploads.c[CadUploadColumn.CAD_FILE_ID],
                        cad_uploads.c[CadUploadColumn.SOURCE_KEY],
                    )
                    .where(
                        cad_uploads.c[CadUploadColumn.STATUS]
                        == CadUploadStatus.PROCESSING
                    )
                    .order_by(cad_uploads.c[CadUploadColumn.UPDATED_AT])
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).first()
            if upload is None:
                return False

            cad_file_id, source_key = upload.cad_file_id, upload.source_key
            locked_id = cad_file_id
            logger.info(f"Processing CAD file {cad_file_id}")
            scan: StepFileScan | None = await asyncio.to_thread(
                _scan, catalog, source_key, stopping, on_progress
            )
            error_code: str | None = await _save_outcome(session, cad_file_id, scan)
    except StopRequested:
        raise
    except Exception:
        if locked_id is not None:
            await _move_to_back(sessions, locked_id)
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
    session: AsyncSession, cad_file_id: str, scan: StepFileScan | None
) -> str | None:
    """Save the outcome of the check and return its error code, None when ready."""
    if scan is None:
        error_code = UPLOAD_NOT_FOUND
    elif not scan.is_valid:
        error_code = INVALID_STEP_FILE
    else:
        try:
            async with session.begin_nested():
                await session.execute(
                    update(cad_uploads)
                    .where(cad_uploads.c[CadUploadColumn.CAD_FILE_ID] == cad_file_id)
                    .values(
                        {
                            CadUploadColumn.STATUS: CadUploadStatus.READY,
                            CadUploadColumn.SHA256: scan.sha256,
                            CadUploadColumn.ERROR_CODE: None,
                        }
                    )
                )
            return None
        except IntegrityError as error:
            if not _violates_sha256_index(error):
                raise
            error_code = DUPLICATE_FILE

    await session.execute(
        update(cad_uploads)
        .where(cad_uploads.c[CadUploadColumn.CAD_FILE_ID] == cad_file_id)
        .values(
            {
                CadUploadColumn.STATUS: CadUploadStatus.FAILED,
                CadUploadColumn.ERROR_CODE: error_code,
            }
        )
    )
    return error_code


async def _move_to_back(
    sessions: async_sessionmaker[AsyncSession], cad_file_id: str
) -> None:
    """Move the file to the back of the queue so it does not block the other files."""
    async with sessions() as session, session.begin():
        locked: str | None = await session.scalar(
            select(cad_uploads.c[CadUploadColumn.CAD_FILE_ID])
            .where(
                cad_uploads.c[CadUploadColumn.CAD_FILE_ID] == cad_file_id,
                cad_uploads.c[CadUploadColumn.STATUS] == CadUploadStatus.PROCESSING,
            )
            .with_for_update(skip_locked=True)
        )
        if locked is not None:
            await session.execute(
                update(cad_uploads)
                .where(cad_uploads.c[CadUploadColumn.CAD_FILE_ID] == cad_file_id)
                .values({CadUploadColumn.UPDATED_AT: func.now()})
            )


def _violates_sha256_index(error: IntegrityError) -> bool:
    return (
        isinstance(error.orig, pg_errors.UniqueViolation)
        and error.orig.diag.constraint_name == SHA256_READY_INDEX
    )
