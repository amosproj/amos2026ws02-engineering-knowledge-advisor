"""Upload state of the records that carry a file (classes marked ``og:file``)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from services.database import ConflictError, Tx


class UploadStatus(StrEnum):
    """Where an uploaded file is in its life cycle."""

    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class Upload:
    """Upload state of one file record.

    Attributes:
        file_id: id of the record the file belongs to.
        status: where the file is in its life cycle.
        error_code: why the file failed, ``None`` unless failed.
        source_key: object storage key of the uploaded file.
        size_bytes: size announced before the upload.
        created_at: when the upload was registered.
        updated_at: last change of the state.
    """

    file_id: str
    status: UploadStatus
    error_code: str | None
    source_key: str
    size_bytes: int
    created_at: datetime
    updated_at: datetime


class LockTimeoutError(ConflictError):
    """A row stayed locked longer than the store waits (``UploadStore.limit_lock_wait``)."""


class DuplicateFileError(ConflictError):
    """A file with the same content is ready already."""


class UploadStore(ABC):
    """Upload state per file record. A file record's upload is deleted with the record."""

    @abstractmethod
    def limit_lock_wait(self, tx: Tx) -> AbstractAsyncContextManager[None]:
        """Inside, every lock in ``tx`` is waited for only briefly, then ``LockTimeoutError`` is raised."""
        ...

    @abstractmethod
    async def start_upload(
        self, file_id: str, source_key: str, size_bytes: int, tx: Tx
    ) -> Upload | None:
        """Registers the upload of ``file_id``'s file, status ``uploading``.

        Replaces an upload that is still ``uploading`` or has ``failed``.

        Returns:
            The new upload, ``None`` if the file is ``processing`` or ``ready``.
        """
        ...

    @abstractmethod
    async def delete_upload(self, file_id: str, tx: Tx) -> None:
        """Deletes the upload state of ``file_id``'s file. The record stays."""
        ...

    @abstractmethod
    async def get_uploads(self, file_ids: Sequence[str], tx: Tx) -> dict[str, Upload]:
        """Returns file id -> upload, for the ids that have one."""
        ...

    @abstractmethod
    async def finish_upload(
        self, file_id: str, error_code: str | None, tx: Tx
    ) -> Upload | None:
        """Moves an uploading file to ``processing``, or to ``failed`` if ``error_code`` is given.

        Returns:
            The changed upload, ``None`` if the file was not uploading (any more).
        """
        ...

    @abstractmethod
    async def lock_next_to_process(self, tx: Tx) -> Upload | None:
        """Locks the upload waiting longest in ``processing`` until ``tx`` ends, skipping locked ones.

        Returns:
            The locked upload, ``None`` if none is waiting.
        """
        ...

    @abstractmethod
    async def set_ready(self, file_id: str, sha256: str, tx: Tx) -> None:
        """Marks the file ``ready`` with its content hash.

        Raises:
            DuplicateFileError: a file with the same content is ready already. ``tx`` stays usable.
        """
        ...

    @abstractmethod
    async def set_failed(self, file_id: str, error_code: str, tx: Tx) -> None:
        """Marks the file ``failed`` with ``error_code``."""
        ...

    @abstractmethod
    async def move_to_back(self, file_id: str, tx: Tx) -> None:
        """Puts a file still in ``processing`` and not locked at the end of the queue."""
        ...

    @abstractmethod
    async def get_abandoned_ids(self, max_age: timedelta, tx: Tx) -> list[str]:
        """Returns the ids of files still ``uploading`` longer than ``max_age`` after their registration."""
        ...

    @abstractmethod
    async def lock_abandoned(
        self, file_id: str, max_age: timedelta, tx: Tx
    ) -> Upload | None:
        """Locks the upload until ``tx`` ends if it is still abandoned and not locked.

        Returns:
            The locked upload, else ``None``.
        """
        ...

    @abstractmethod
    async def get_kept_ids(self, file_ids: Sequence[str], tx: Tx) -> set[str]:
        """Returns those of ``file_ids`` whose upload exists and has not failed."""
        ...
