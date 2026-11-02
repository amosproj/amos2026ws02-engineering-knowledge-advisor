from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from itertools import batched

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from db import Machine, MachineStatus, get_engine
from logger import logger
from storage.s3 import DELETE_BATCH_SIZE, delete_objects, list_objects

ABANDONED_UPLOAD_AGE = timedelta(hours=24)

ORPHAN_OBJECT_AGE = timedelta(hours=24)
MACHINES_PREFIX = "machines/"


def expire_abandoned_uploads() -> None:
    """Delete the imports still uploading 24 h after their creation, with their object."""
    with Session(get_engine()) as session:
        object_keys = session.scalars(
            delete(Machine)
            .where(
                Machine.status == MachineStatus.UPLOADING,
                Machine.created_at < func.now() - ABANDONED_UPLOAD_AGE,
            )
            .returning(Machine.object_key)
        ).all()
        session.commit()

    # If the storage fails, the objects left are removed later as orphans
    for batch in batched(object_keys, DELETE_BATCH_SIZE):
        delete_objects(list(batch))
    if object_keys:
        logger.info(f"Expired {len(object_keys)} abandoned uploads")


def delete_orphan_objects(on_progress: Callable[[], None]) -> None:
    """Delete the objects older than 24 h that no machine still in use points to.

    This covers the objects of failed machines whose deletion failed, and uploads that
    landed after their import was cancelled.
    """
    cutoff = datetime.now(UTC) - ORPHAN_OBJECT_AGE
    deleted = 0
    for page in list_objects(MACHINES_PREFIX):
        object_keys = [obj["Key"] for obj in page if obj["LastModified"] < cutoff]
        if object_keys:
            with Session(get_engine()) as session:
                used_keys = set(
                    session.scalars(
                        select(Machine.object_key).where(
                            Machine.object_key.in_(object_keys),
                            Machine.status != MachineStatus.FAILED,
                        )
                    )
                )
            orphan_keys = [key for key in object_keys if key not in used_keys]
            delete_objects(orphan_keys)
            deleted += len(orphan_keys)
        on_progress()

    if deleted:
        logger.info(f"Deleted {deleted} orphan objects")
