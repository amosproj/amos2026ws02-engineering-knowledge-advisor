import asyncio
import threading
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from logger import logger
from services import ConflictError
from services.catalog import CatalogService
from services.catalog.files import FILES_PREFIX, get_cad_file_id
from services.object_storage import StoredObject
from services.uploads import Upload

ABANDONED_UPLOAD_AGE: timedelta = timedelta(hours=24)

ORPHAN_OBJECT_AGE: timedelta = timedelta(hours=24)


async def expire_abandoned_uploads(
    sessions: async_sessionmaker[AsyncSession],
    catalog: CatalogService,
    stopping: threading.Event,
    on_progress: Callable[[], None],
) -> None:
    """Delete the uploads still uploading 24 h after their creation, with their folder. The file records stay."""
    async with sessions() as session:
        cad_file_ids: Sequence[str] = await catalog.uploads.get_abandoned_ids(
            ABANDONED_UPLOAD_AGE, session
        )

    expired = 0
    for cad_file_id in cad_file_ids:
        if stopping.is_set():
            break
        on_progress()
        # one transaction per file, so a conflict with a deletion from the API only skips this file
        try:
            async with sessions() as session, session.begin():
                upload: Upload | None = await catalog.uploads.lock_abandoned(
                    cad_file_id, ABANDONED_UPLOAD_AGE, session
                )
                if upload is None:
                    continue
                source_key: str = upload.source_key
                await catalog.uploads.delete_upload(cad_file_id, session)
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
    pages: Iterator[list[StoredObject]] = catalog.storage.list_objects(FILES_PREFIX)
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
                kept_ids: set[str] = await catalog.uploads.get_kept_ids(
                    sorted(set(cad_file_ids.values())), session
                )
            orphan_keys: list[str] = [
                key for key, cad_id in cad_file_ids.items() if cad_id not in kept_ids
            ]
            await asyncio.to_thread(catalog.storage.delete_objects, orphan_keys)
            deleted += len(orphan_keys)
        on_progress()

    if deleted:
        logger.info(f"Deleted {deleted} orphan objects")
