import asyncio
import tempfile
import threading
import time
from collections.abc import Callable, Generator, Iterator
from contextlib import closing
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cad_file_worker.conversion import convert_step_file
from cad_file_worker.errors import ConversionTimeoutError, StopRequested
from cad_file_worker.step_file import StepFileScan, scan_step_file
from logger import logger
from services import UnstorableValueError
from services.cad.errors import StepImportError
from services.cad.model import CadModel
from services.catalog import CatalogService
from services.ograg.service import ParentLimitError, RecordError
from services.uploads import Upload, UploadStore

CHUNK_SIZE = 8 * 1024 * 1024
MAX_PROCESSING_SECONDS = 30 * 60
MAX_CONVERSION_SECONDS = 30 * 60

UPLOAD_NOT_FOUND = "upload_not_found"
INVALID_STEP_FILE = "invalid_step_file"
PARSE_ERROR = "parse_error"
IMPORT_ERROR = "import_error"
PROCESSING_TIMEOUT = "processing_timeout"


async def process_next_cad_upload(
    sessions: async_sessionmaker[AsyncSession],
    catalog: CatalogService,
    stopping: threading.Event,
    on_progress: Callable[[], None],
) -> bool:
    """Check, convert and import the STEP file waiting longest in processing. Returns False when no file is waiting.

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
            error_code: str | None = await _process(
                catalog, session, upload, stopping, on_progress
            )
            if error_code is not None:
                await catalog.uploads.set_failed(cad_file_id, error_code, session)
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


async def _process(
    catalog: CatalogService,
    session: AsyncSession,
    upload: Upload,
    stopping: threading.Event,
    on_progress: Callable[[], None],
) -> str | None:
    """Check, convert and import the file, then mark it ready. Returns the error code, None when ready."""
    with tempfile.TemporaryDirectory(prefix="cad-file-") as folder:
        step_path: Path = Path(folder) / "source.step"
        scan: StepFileScan | None = await asyncio.to_thread(
            _scan, catalog, upload.source_key, step_path, stopping, on_progress
        )
        if scan is None:
            return UPLOAD_NOT_FOUND
        if not scan.is_valid:
            return INVALID_STEP_FILE
        error_code: str | None = await _convert_and_import(
            catalog, session, upload.file_id, step_path, stopping, on_progress
        )
    if error_code is None:
        await catalog.uploads.set_ready(upload.file_id, scan.sha256, session)
    return error_code


def _scan(
    catalog: CatalogService,
    source_key: str,
    step_path: Path,
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
    with closing(chunks), step_path.open("wb") as file:
        return scan_step_file(_copy(_watch(chunks, stopping, on_progress), file))


def _copy(chunks: Iterator[bytes], file: BinaryIO) -> Iterator[bytes]:
    for chunk in chunks:
        file.write(chunk)
        yield chunk


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


async def _convert_and_import(
    catalog: CatalogService,
    session: AsyncSession,
    cad_file_id: str,
    step_path: Path,
    stopping: threading.Event,
    on_progress: Callable[[], None],
) -> str | None:
    """Convert the STEP file and import its assembly tree. Returns the error code, None when imported."""
    try:
        model: CadModel = await asyncio.to_thread(
            convert_step_file,
            step_path,
            step_path.with_name("model.glb"),
            MAX_CONVERSION_SECONDS,
            stopping,
            on_progress,
        )
    except StepImportError as error:
        logger.warning(f"CAD file {cad_file_id} cannot be parsed: {error}")
        return PARSE_ERROR
    except ConversionTimeoutError as error:
        logger.warning(f"CAD file {cad_file_id}: {error}")
        return PROCESSING_TIMEOUT

    try:
        # the failure is saved in the same transaction, so a refused import must not abort it
        async with session.begin_nested():
            warnings: list[str] = await catalog.import_cad_file_tree(
                session, cad_file_id, model
            )
    except (RecordError, ParentLimitError, UnstorableValueError) as error:
        logger.warning(f"CAD file {cad_file_id} cannot be imported: {error}")
        return IMPORT_ERROR
    for warning in warnings:
        logger.warning(f"CAD file {cad_file_id}: {warning}")
    return None


async def _move_to_back(
    sessions: async_sessionmaker[AsyncSession],
    uploads: UploadStore,
    cad_file_id: str,
) -> None:
    """Move the file to the back of the queue so it does not block the other files."""
    async with sessions() as session, session.begin():
        await uploads.move_to_back(cad_file_id, session)
