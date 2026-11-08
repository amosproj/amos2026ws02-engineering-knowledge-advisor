from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, override

from psycopg import errors as pg_errors
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
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.names import SHA256_READY_INDEX, CadUploadColumn, CadUploadStatus
from db.tables import Tables
from services.postgres.shared import Conditions
from services.uploads import (
    DuplicateFileError,
    LockTimeoutError,
    Upload,
    UploadStatus,
    UploadStore,
)

# the worker keeps the row of the file it processes locked
LOCK_TIMEOUT: str = "2s"
LOCK_NOT_AVAILABLE: str = "55P03"
SET_LOCK_TIMEOUT: str = f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"
ERROR_LOCK_TIMEOUT: str = "a row stayed locked longer than {timeout}"
ERROR_DUPLICATE_FILE: str = "a file with the same content is ready already: {file_id!r}"


class PgUploadStore(UploadStore):
    """Upload state in the ``cad_uploads`` table. Every method runs in the caller's ``AsyncSession``."""

    def __init__(self, tables: Tables) -> None:
        self.table: Table = tables.cad_uploads

    @override
    @asynccontextmanager
    async def limit_lock_wait(self, tx: AsyncSession) -> AsyncIterator[None]:
        await tx.execute(text(SET_LOCK_TIMEOUT))
        try:
            yield
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) != LOCK_NOT_AVAILABLE:
                raise
            raise LockTimeoutError(
                ERROR_LOCK_TIMEOUT.format(timeout=LOCK_TIMEOUT)
            ) from exc

    @override
    async def start_upload(
        self, file_id: str, source_key: str, size_bytes: int, tx: AsyncSession
    ) -> Upload | None:
        restarted: dict[CadUploadColumn, Any] = {
            CadUploadColumn.STATUS: CadUploadStatus.UPLOADING,
            CadUploadColumn.ERROR_CODE: None,
            CadUploadColumn.SHA256: None,
            CadUploadColumn.SOURCE_KEY: source_key,
            CadUploadColumn.SIZE_BYTES: size_bytes,
            CadUploadColumn.CREATED_AT: func.now(),
            CadUploadColumn.UPDATED_AT: func.now(),
        }
        row: RowMapping | None = (
            (
                await tx.execute(
                    insert(self.table)
                    .values(
                        {
                            CadUploadColumn.CAD_FILE_ID: file_id,
                            CadUploadColumn.SOURCE_KEY: source_key,
                            CadUploadColumn.SIZE_BYTES: size_bytes,
                        }
                    )
                    # a file in processing or ready is kept
                    .on_conflict_do_update(
                        index_elements=[self._get_file_id_column()],
                        set_=restarted,
                        where=Conditions.match_any(
                            self.table.c[CadUploadColumn.STATUS],
                            [CadUploadStatus.UPLOADING, CadUploadStatus.FAILED],
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
        status: CadUploadStatus = (
            CadUploadStatus.PROCESSING if error_code is None else CadUploadStatus.FAILED
        )
        row: RowMapping | None = (
            (
                await tx.execute(
                    update(self.table)
                    .where(
                        self._get_file_id_column() == file_id,
                        self._has_status(CadUploadStatus.UPLOADING),
                    )
                    .values(
                        {
                            CadUploadColumn.STATUS: status,
                            CadUploadColumn.ERROR_CODE: error_code,
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
                    .where(self._has_status(CadUploadStatus.PROCESSING))
                    .order_by(self.table.c[CadUploadColumn.UPDATED_AT])
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else _to_upload(row)

    @override
    async def set_ready(self, file_id: str, sha256: str, tx: AsyncSession) -> None:
        try:
            async with tx.begin_nested():
                await self._set_values(
                    file_id,
                    {
                        CadUploadColumn.STATUS: CadUploadStatus.READY,
                        CadUploadColumn.SHA256: sha256,
                        CadUploadColumn.ERROR_CODE: None,
                    },
                    tx,
                )
        except IntegrityError as exc:
            if not _violates_sha256_index(exc):
                raise
            raise DuplicateFileError(
                ERROR_DUPLICATE_FILE.format(file_id=file_id)
            ) from exc

    @override
    async def set_failed(self, file_id: str, error_code: str, tx: AsyncSession) -> None:
        await self._set_values(
            file_id,
            {
                CadUploadColumn.STATUS: CadUploadStatus.FAILED,
                CadUploadColumn.ERROR_CODE: error_code,
            },
            tx,
        )

    @override
    async def move_to_back(self, file_id: str, tx: AsyncSession) -> None:
        locked_id: str | None = await tx.scalar(
            select(self._get_file_id_column())
            .where(
                self._get_file_id_column() == file_id,
                self._has_status(CadUploadStatus.PROCESSING),
            )
            .with_for_update(skip_locked=True)
        )
        if locked_id is not None:
            await self._set_values(
                file_id, {CadUploadColumn.UPDATED_AT: func.now()}, tx
            )

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
                    self.table.c[CadUploadColumn.STATUS] != CadUploadStatus.FAILED,
                )
            )
        )

    def _get_file_id_column(self) -> Column[str]:
        return self.table.c[CadUploadColumn.CAD_FILE_ID]

    def _has_status(self, status: CadUploadStatus) -> ColumnElement[bool]:
        return self.table.c[CadUploadColumn.STATUS] == status

    def _is_abandoned(self, max_age: timedelta) -> tuple[ColumnElement[bool], ...]:
        return (
            self._has_status(CadUploadStatus.UPLOADING),
            self.table.c[CadUploadColumn.CREATED_AT] < func.now() - max_age,
        )

    async def _set_values(
        self, file_id: str, values: dict[CadUploadColumn, Any], tx: AsyncSession
    ) -> None:
        await tx.execute(
            update(self.table)
            .where(self._get_file_id_column() == file_id)
            .values(values)
        )


def _to_upload(row: RowMapping) -> Upload:
    return Upload(
        file_id=row[CadUploadColumn.CAD_FILE_ID],
        status=UploadStatus(row[CadUploadColumn.STATUS]),
        error_code=row[CadUploadColumn.ERROR_CODE],
        source_key=row[CadUploadColumn.SOURCE_KEY],
        size_bytes=row[CadUploadColumn.SIZE_BYTES],
        created_at=row[CadUploadColumn.CREATED_AT],
        updated_at=row[CadUploadColumn.UPDATED_AT],
    )


def _violates_sha256_index(exc: IntegrityError) -> bool:
    return (
        isinstance(exc.orig, pg_errors.UniqueViolation)
        and exc.orig.diag.constraint_name == SHA256_READY_INDEX
    )
