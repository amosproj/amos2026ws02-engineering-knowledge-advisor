import asyncio
import threading
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db import CadUploadColumn, CadUploadStatus, cad_uploads
from logger import logger
from services import ConflictError
from services.catalog import CatalogService
from services.catalog.files import MACHINES_PREFIX, get_cad_file_id
from services.catalog.records import delete_cad_file
from services.object_storage import StoredObject

ABANDONED_UPLOAD_AGE: timedelta = timedelta(hours=24)

ORPHAN_OBJECT_AGE: timedelta = timedelta(hours=24)


async def expire_abandoned_uploads(
    sessions: async_sessionmaker[AsyncSession],
    catalog: CatalogService,
    stopping: threading.Event,
    on_progress: Callable[[], None],
) -> None:
    """Delete the CAD files still uploading 24 h after their creation, with their folder."""
    is_abandoned: tuple[ColumnElement[bool], ...] = (
        cad_uploads.c[CadUploadColumn.STATUS] == CadUploadStatus.UPLOADING,
        cad_uploads.c[CadUploadColumn.CREATED_AT] < func.now() - ABANDONED_UPLOAD_AGE,
    )
    async with sessions() as session:
        cad_file_ids: Sequence[str] = (
            await session.scalars(
                select(cad_uploads.c[CadUploadColumn.CAD_FILE_ID]).where(*is_abandoned)
            )
        ).all()

    expired = 0
    for cad_file_id in cad_file_ids:
        if stopping.is_set():
            break
        on_progress()
        # one transaction per file, so a conflict with a deletion from the API only skips this file
        try:
            async with sessions() as session, session.begin():
                source_key: str | None = await session.scalar(
                    select(cad_uploads.c[CadUploadColumn.SOURCE_KEY])
                    .where(
                        cad_uploads.c[CadUploadColumn.CAD_FILE_ID] == cad_file_id,
                        *is_abandoned,
                    )
                    .with_for_update(skip_locked=True)
                )
                if source_key is None:
                    continue
                await delete_cad_file(catalog.ograg, session, cad_file_id)
        except ConflictError:
            logger.warning(f"Could not expire CAD file {cad_file_id}, retrying later")
            continue
        # if the storage fails, the objects left are removed later as orphans
        await asyncio.to_thread(catalog.delete_source_folders, [source_key])
        expired += 1

    if expired:
        logger.info(f"Expired {expired} abandoned uploads")


async def delete_orphan_objects(
    sessions: async_sessionmaker[AsyncSession],
    catalog: CatalogService,
    stopping: threading.Event,
    on_progress: Callable[[], None],
) -> None:
    """Delete the objects older than 24 h whose CAD file no longer exists or failed.

    This covers the folders whose deletion failed, and uploads that landed after their file
    was deleted or failed.
    """
    cutoff: datetime = datetime.now(UTC) - ORPHAN_OBJECT_AGE
    pages: Iterator[list[StoredObject]] = catalog.storage.list_objects(MACHINES_PREFIX)
    deleted = 0
    # listing fetches the pages lazily, so each page is fetched off the event loop
    while (
        not stopping.is_set()
        and (page := await asyncio.to_thread(next, pages, None)) is not None
    ):
        cad_file_ids: dict[str, str] = {}
        for obj in page:
            if obj.last_modified >= cutoff:
                continue
            cad_file_id: str | None = get_cad_file_id(obj.key)
            if cad_file_id is None:
                logger.warning(
                    f"Skipping object {obj.key} outside of a CAD file folder"
                )
                continue
            cad_file_ids[obj.key] = cad_file_id

        if cad_file_ids:
            async with sessions() as session:
                kept_ids: set[str] = set(
                    await session.scalars(
                        select(cad_uploads.c[CadUploadColumn.CAD_FILE_ID]).where(
                            cad_uploads.c[CadUploadColumn.CAD_FILE_ID].in_(
                                set(cad_file_ids.values())
                            ),
                            cad_uploads.c[CadUploadColumn.STATUS]
                            != CadUploadStatus.FAILED,
                        )
                    )
                )
            orphan_keys: list[str] = [
                key for key, cad_id in cad_file_ids.items() if cad_id not in kept_ids
            ]
            await asyncio.to_thread(catalog.storage.delete_objects, orphan_keys)
            deleted += len(orphan_keys)
        on_progress()

    if deleted:
        logger.info(f"Deleted {deleted} orphan objects")
