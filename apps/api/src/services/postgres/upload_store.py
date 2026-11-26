from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import override

from sqlalchemy import (
    ColumnElement,
    Table,
    delete,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UploadModel
from db.names import UploadColumn
from services.postgres.shared import Conditions, Statements
from services.uploads import (
    LockTimeoutError,
    UpAxis,
    Upload,
    UploadStatus,
    UploadStore,
)

# the worker keeps the row of the file it processes locked
LOCK_TIMEOUT: str = "2s"
LOCK_NOT_AVAILABLE: str = "55P03"
# the worker importing a file waits for its record, which a request holds while waiting for the upload
DEADLOCK_DETECTED: str = "40P01"
SET_LOCK_TIMEOUT: str = f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"
ERROR_LOCK_TIMEOUT: str = "a row stayed locked longer than {timeout}"


class PgUploadStore(UploadStore):
    """Upload state in the ``uploads`` table. Every method runs in the caller's ``AsyncSession``."""

    def __init__(self) -> None:
        self.table: Table = UploadModel.get_table()

    @override
    @asynccontextmanager
    async def limit_lock_wait(self, tx: AsyncSession) -> AsyncGenerator[None]:
        await tx.execute(text(SET_LOCK_TIMEOUT))
        try:
            yield
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) not in (
                LOCK_NOT_AVAILABLE,
                DEADLOCK_DETECTED,
            ):
                raise
            raise LockTimeoutError(
                ERROR_LOCK_TIMEOUT.format(timeout=LOCK_TIMEOUT)
            ) from exc

    @override
    async def start_upload(
        self, file_id: str, source_key: str, size_bytes: int, tx: AsyncSession
    ) -> Upload | None:
        restarted: dict[UploadColumn, object] = {
            UploadColumn.STATUS: UploadStatus.UPLOADING,
            UploadColumn.ERROR_CODE: None,
            UploadColumn.SHA256: None,
            UploadColumn.MODEL_KEY: None,
            UploadColumn.PREVIEW_KEY: None,
            UploadColumn.SOURCE_KEY: source_key,
            UploadColumn.SIZE_BYTES: size_bytes,
            UploadColumn.CREATED_AT: func.now(),
            UploadColumn.UPDATED_AT: func.now(),
        }
        row: UploadModel | None = (
            await tx.scalars(
                Statements.overwrite_loaded(
                    insert(UploadModel)
                    .values(
                        {
                            UploadColumn.FILE_ID: file_id,
                            UploadColumn.SOURCE_KEY: source_key,
                            UploadColumn.SIZE_BYTES: size_bytes,
                        }
                    )
                    # a file in processing or ready is kept
                    .on_conflict_do_update(
                        index_elements=[UploadModel.file_id],
                        set_=restarted,
                        where=Conditions.match_any(
                            UploadModel.status,
                            [UploadStatus.UPLOADING, UploadStatus.FAILED],
                        ),
                    )
                    .returning(UploadModel)
                )
            )
        ).first()
        return None if row is None else _to_upload(row)

    @override
    async def delete_upload(self, file_id: str, tx: AsyncSession) -> None:
        await tx.execute(delete(self.table).where(UploadModel.file_id == file_id))

    @override
    async def get_uploads(
        self, file_ids: Sequence[str], tx: AsyncSession
    ) -> dict[str, Upload]:
        if not file_ids:
            return {}
        rows: Sequence[UploadModel] = (
            await tx.scalars(
                Statements.overwrite_loaded(
                    select(UploadModel).where(
                        Conditions.match_any(UploadModel.file_id, file_ids)
                    )
                )
            )
        ).all()
        uploads: list[Upload] = [_to_upload(row) for row in rows]
        return {upload.file_id: upload for upload in uploads}

    @override
    async def finish_upload(
        self, file_id: str, error_code: str | None, tx: AsyncSession
    ) -> Upload | None:
        status: UploadStatus = (
            UploadStatus.PROCESSING if error_code is None else UploadStatus.FAILED
        )
        row: UploadModel | None = (
            await tx.scalars(
                Statements.overwrite_loaded(
                    update(UploadModel)
                    .where(
                        UploadModel.file_id == file_id,
                        self._has_status(UploadStatus.UPLOADING),
                    )
                    .values(
                        {
                            UploadColumn.STATUS: status,
                            UploadColumn.ERROR_CODE: error_code,
                        }
                    )
                    .returning(UploadModel)
                )
            )
        ).first()
        return None if row is None else _to_upload(row)

    @override
    async def lock_next_to_process(self, tx: AsyncSession) -> Upload | None:
        row: UploadModel | None = await tx.scalar(
            Statements.overwrite_loaded(
                select(UploadModel)
                .where(self._has_status(UploadStatus.PROCESSING))
                .order_by(UploadModel.updated_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        )
        return None if row is None else _to_upload(row)

    @override
    async def set_ready(
        self,
        file_id: str,
        sha256: str,
        model_key: str | None,
        preview_key: str | None,
        tx: AsyncSession,
    ) -> None:
        await self._set_values(
            file_id,
            {
                UploadColumn.STATUS: UploadStatus.READY,
                UploadColumn.SHA256: sha256,
                UploadColumn.MODEL_KEY: model_key,
                UploadColumn.PREVIEW_KEY: preview_key,
                UploadColumn.ERROR_CODE: None,
            },
            tx,
        )

    @override
    async def set_failed(self, file_id: str, error_code: str, tx: AsyncSession) -> None:
        await self._set_values(
            file_id,
            {
                UploadColumn.STATUS: UploadStatus.FAILED,
                UploadColumn.ERROR_CODE: error_code,
            },
            tx,
        )

    @override
    async def set_up_axis(
        self, file_id: str, up_axis: UpAxis, tx: AsyncSession
    ) -> Upload | None:
        row: UploadModel | None = (
            await tx.scalars(
                Statements.overwrite_loaded(
                    update(UploadModel)
                    .where(
                        UploadModel.file_id == file_id,
                        self._has_status(UploadStatus.READY),
                    )
                    .values(
                        {
                            UploadColumn.UP_AXIS: up_axis,
                            # keeps the last status change
                            UploadColumn.UPDATED_AT: UploadModel.updated_at,
                        }
                    )
                    .returning(UploadModel)
                )
            )
        ).first()
        return None if row is None else _to_upload(row)

    @override
    async def move_to_back(self, file_id: str, tx: AsyncSession) -> None:
        locked_id: str | None = await tx.scalar(
            select(UploadModel.file_id)
            .where(
                UploadModel.file_id == file_id,
                self._has_status(UploadStatus.PROCESSING),
            )
            .with_for_update(skip_locked=True)
        )
        if locked_id is not None:
            await self._set_values(file_id, {UploadColumn.UPDATED_AT: func.now()}, tx)

    @override
    async def get_abandoned_ids(
        self, max_age: timedelta, tx: AsyncSession
    ) -> list[str]:
        return list(
            await tx.scalars(
                select(UploadModel.file_id).where(*self._is_abandoned(max_age))
            )
        )

    @override
    async def lock_abandoned(
        self, file_id: str, max_age: timedelta, tx: AsyncSession
    ) -> Upload | None:
        row: UploadModel | None = await tx.scalar(
            Statements.overwrite_loaded(
                select(UploadModel)
                .where(
                    UploadModel.file_id == file_id,
                    *self._is_abandoned(max_age),
                )
                .with_for_update(skip_locked=True)
            )
        )
        return None if row is None else _to_upload(row)

    @override
    async def get_kept_ids(self, file_ids: Sequence[str], tx: AsyncSession) -> set[str]:
        if not file_ids:
            return set()
        return set(
            await tx.scalars(
                select(UploadModel.file_id).where(
                    Conditions.match_any(UploadModel.file_id, file_ids),
                    UploadModel.status != UploadStatus.FAILED,
                )
            )
        )

    def _has_status(self, status: UploadStatus) -> ColumnElement[bool]:
        return UploadModel.status == status

    def _is_abandoned(self, max_age: timedelta) -> tuple[ColumnElement[bool], ...]:
        return (
            self._has_status(UploadStatus.UPLOADING),
            UploadModel.created_at < func.now() - max_age,
        )

    async def _set_values(
        self, file_id: str, values: dict[UploadColumn, object], tx: AsyncSession
    ) -> None:
        await tx.execute(
            update(self.table).where(UploadModel.file_id == file_id).values(values)
        )


def _to_upload(row: UploadModel) -> Upload:
    return Upload(
        file_id=row.file_id,
        status=UploadStatus(row.status),
        error_code=row.error_code,
        source_key=row.source_key,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
        updated_at=row.updated_at,
        model_key=row.model_key,
        preview_key=row.preview_key,
        up_axis=UpAxis(row.up_axis),
    )
