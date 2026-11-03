import asyncio
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db import CadUploadStatus, cad_uploads
from logger import logger
from services import ConflictError
from services.catalog import delete_cad_file
from services.ograg.service import OgRagService
from storage.s3 import delete_objects, delete_source_folders, list_objects

ABANDONED_UPLOAD_AGE = timedelta(hours=24)

ORPHAN_OBJECT_AGE = timedelta(hours=24)
MACHINES_PREFIX = "machines/"


async def expire_abandoned_uploads(
    sessions: async_sessionmaker[AsyncSession],
    ograg: OgRagService,
    stopping: threading.Event,
    on_progress: Callable[[], None],
) -> None:
    """Delete the CAD files still uploading 24 h after their creation, with their folder."""
    is_abandoned = (
        cad_uploads.c.status == CadUploadStatus.UPLOADING,
        cad_uploads.c.created_at < func.now() - ABANDONED_UPLOAD_AGE,
    )
    async with sessions() as session:
        cad_file_ids = (
            await session.scalars(
                select(cad_uploads.c.cad_file_id).where(*is_abandoned)
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
                source_key = await session.scalar(
                    select(cad_uploads.c.source_key)
                    .where(cad_uploads.c.cad_file_id == cad_file_id, *is_abandoned)
                    .with_for_update(skip_locked=True)
                )
                if source_key is None:
                    continue
                await delete_cad_file(ograg, session, cad_file_id)
        except ConflictError:
            logger.warning(f"Could not expire CAD file {cad_file_id}, retrying later")
            continue
        # if the storage fails, the objects left are removed later as orphans
        await asyncio.to_thread(delete_source_folders, [source_key])
        expired += 1

    if expired:
        logger.info(f"Expired {expired} abandoned uploads")


async def delete_orphan_objects(
    sessions: async_sessionmaker[AsyncSession],
    stopping: threading.Event,
    on_progress: Callable[[], None],
) -> None:
    """Delete the objects older than 24 h whose CAD file no longer exists or failed.

    This covers the folders whose deletion failed, and uploads that landed after their file
    was deleted or failed.
    """
    cutoff = datetime.now(UTC) - ORPHAN_OBJECT_AGE
    pages = list_objects(MACHINES_PREFIX)
    deleted = 0
    # listing fetches the pages lazily, so each page is fetched off the event loop
    while (
        not stopping.is_set()
        and (page := await asyncio.to_thread(next, pages, None)) is not None
    ):
        cad_file_ids: dict[str, str] = {}
        for obj in page:
            key, modified = obj.get("Key"), obj.get("LastModified")
            if key is None or modified is None or modified >= cutoff:
                continue
            cad_file_id = _get_cad_file_id(key)
            if cad_file_id is None:
                logger.warning(f"Skipping object {key} outside of a CAD file folder")
                continue
            cad_file_ids[key] = cad_file_id

        if cad_file_ids:
            async with sessions() as session:
                kept_ids = set(
                    await session.scalars(
                        select(cad_uploads.c.cad_file_id).where(
                            cad_uploads.c.cad_file_id.in_(set(cad_file_ids.values())),
                            cad_uploads.c.status != CadUploadStatus.FAILED,
                        )
                    )
                )
            orphan_keys = [
                key for key, cad_id in cad_file_ids.items() if cad_id not in kept_ids
            ]
            await asyncio.to_thread(delete_objects, orphan_keys)
            deleted += len(orphan_keys)
        on_progress()

    if deleted:
        logger.info(f"Deleted {deleted} orphan objects")


def _get_cad_file_id(key: str) -> str | None:
    """The CAD file id in machines/{machine}/assembly-groups/{group}/cad-files/{cad_file}/..."""
    parts = key.split("/")
    if len(parts) < 7 or parts[2] != "assembly-groups" or parts[4] != "cad-files":
        return None
    return parts[5]
