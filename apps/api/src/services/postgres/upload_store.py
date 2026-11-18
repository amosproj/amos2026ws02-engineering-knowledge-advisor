from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, override

from sqlalchemy import (
    Column,
    ColumnElement,
    RowMapping,
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

from db.names import UploadColumn
from db.tables import Tables
from services.postgres.shared import Conditions
from services.uploads import (
    LockTimeoutError,
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

    def __init__(self, tables: Tables) -> None:
        self.table: Table = tables.uploads

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
        restarted: dict[UploadColumn, Any] = {
            UploadColumn.STATUS: UploadStatus.UPLOADING,
            UploadColumn.ERROR_CODE: None,
            UploadColumn.SHA256: None,
            UploadColumn.MODEL_KEY: None,
            UploadColumn.SOURCE_KEY: source_key,
            UploadColumn.SIZE_BYTES: size_bytes,
            UploadColumn.CREATED_AT: func.now(),
            UploadColumn.UPDATED_AT: func.now(),
        }
        row: RowMapping | None = (
            (
                await tx.execute(
                    insert(self.table)
                    .values(
                        {
                            UploadColumn.FILE_ID: file_id,
                            UploadColumn.SOURCE_KEY: source_key,
                            UploadColumn.SIZE_BYTES: size_bytes,
                        }
                    )
                    # a file in processing or ready is kept
                    .on_conflict_do_update(
                        index_elements=[self._get_file_id_column()],
                        set_=restarted,
                        where=Conditions.match_any(
                            self.table.c[UploadColumn.STATUS],
                            [UploadStatus.UPLOADING, UploadStatus.FAILED],
                        ),
                    )
                    .returning(*self.table.c)
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else _to_upload(row)

    @override
    async def delete_upload(self, file_id: str, tx: AsyncSession) -> None:
        await tx.execute(
            delete(self.table).where(self._get_file_id_column() == file_id)
        )

    @override
    async def get_uploads(
        self, file_ids: Sequence[str], tx: AsyncSession
    ) -> dict[str, Upload]:
        if not file_ids:
            return {}
        rows: Sequence[RowMapping] = (
            (
                await tx.execute(
                    select(self.table).where(
                        Conditions.match_any(self._get_file_id_column(), file_ids)
                    )
                )
            )
            .mappings()
            .all()
        )
        uploads: list[Upload] = [_to_upload(row) for row in rows]
        return {upload.file_id: upload for upload in uploads}

    @override
    async def finish_upload(
        self, file_id: str, error_code: str | None, tx: AsyncSession
    ) -> Upload | None:
        status: UploadStatus = (
            UploadStatus.PROCESSING if error_code is None else UploadStatus.FAILED
        )
        row: RowMapping | None = (
            (
                await tx.execute(
                    update(self.table)
                    .where(
                        self._get_file_id_column() == file_id,
                        self._has_status(UploadStatus.UPLOADING),
                    )
                    .values(
                        {
                            UploadColumn.STATUS: status,
                            UploadColumn.ERROR_CODE: error_code,
                        }
                    )
                    .returning(*self.table.c)
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else _to_upload(row)

    @override
    async def lock_next_to_process(self, tx: AsyncSession) -> Upload | None:
        row: RowMapping | None = (
            (
                await tx.execute(
                    select(self.table)
                    .where(self._has_status(UploadStatus.PROCESSING))
                    .order_by(self.table.c[UploadColumn.UPDATED_AT])
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else _to_upload(row)

    @override
    async def set_ready(
        self, file_id: str, sha256: str, model_key: str | None, tx: AsyncSession
    ) -> None:
        await self._set_values(
            file_id,
            {
                UploadColumn.STATUS: UploadStatus.READY,
                UploadColumn.SHA256: sha256,
                UploadColumn.MODEL_KEY: model_key,
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
    async def move_to_back(self, file_id: str, tx: AsyncSession) -> None:
        locked_id: str | None = await tx.scalar(
            select(self._get_file_id_column())
            .where(
                self._get_file_id_column() == file_id,
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
                select(self._get_file_id_column()).where(*self._is_abandoned(max_age))
            )
        )

    @override
    async def lock_abandoned(
        self, file_id: str, max_age: timedelta, tx: AsyncSession
    ) -> Upload | None:
        row: RowMapping | None = (
            (
                await tx.execute(
                    select(self.table)
                    .where(
                        self._get_file_id_column() == file_id,
                        *self._is_abandoned(max_age),
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else _to_upload(row)

    @override
    async def get_kept_ids(self, file_ids: Sequence[str], tx: AsyncSession) -> set[str]:
        if not file_ids:
            return set()
        return set(
            await tx.scalars(
                select(self._get_file_id_column()).where(
                    Conditions.match_any(self._get_file_id_column(), file_ids),
                    self.table.c[UploadColumn.STATUS] != UploadStatus.FAILED,
                )
            )
        )

    def _get_file_id_column(self) -> Column[str]:
        return self.table.c[UploadColumn.FILE_ID]

    def _has_status(self, status: UploadStatus) -> ColumnElement[bool]:
        return self.table.c[UploadColumn.STATUS] == status

    def _is_abandoned(self, max_age: timedelta) -> tuple[ColumnElement[bool], ...]:
        return (
            self._has_status(UploadStatus.UPLOADING),
            self.table.c[UploadColumn.CREATED_AT] < func.now() - max_age,
        )

    async def _set_values(
        self, file_id: str, values: dict[UploadColumn, Any], tx: AsyncSession
    ) -> None:
        await tx.execute(
            update(self.table)
            .where(self._get_file_id_column() == file_id)
            .values(values)
        )


def _to_upload(row: RowMapping) -> Upload:
    return Upload(
        file_id=row[UploadColumn.FILE_ID],
        status=UploadStatus(row[UploadColumn.STATUS]),
        error_code=row[UploadColumn.ERROR_CODE],
        source_key=row[UploadColumn.SOURCE_KEY],
        size_bytes=row[UploadColumn.SIZE_BYTES],
        created_at=row[UploadColumn.CREATED_AT],
        updated_at=row[UploadColumn.UPDATED_AT],
        model_key=row[UploadColumn.MODEL_KEY],
    )
