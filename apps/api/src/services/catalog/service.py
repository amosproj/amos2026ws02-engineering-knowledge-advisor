"""Machines, assembly groups and CAD files with their upload state and stored files.

Every method runs in the caller's session and does not commit. Objects are deleted only after
the commit: the methods that delete return the source keys to pass to ``delete_source_folders``.
"""

import asyncio
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Result, Row, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from db import CadUploadColumn, CadUploadStatus, cad_uploads
from model import (
    AssemblyGroup,
    CadFile,
    CadFileUpload,
    Machine,
    MachineDetails,
    MachineStatus,
    UploadForm,
)
from model.request import FileToUpload
from services import Json, Record
from services.catalog import records
from services.catalog.errors import (
    BusyError,
    ImportFailedError,
    NotFoundError,
    UploadNotFoundError,
)
from services.catalog.files import get_folder, get_source_key
from services.catalog.records import (
    ASSEMBLY_GROUP,
    CAD_FILE,
    ERROR_NOT_FOUND,
    MACHINE,
    PART_OF,
    Fields,
)
from services.object_storage import ObjectStorage
from services.ograg.service import OgRagService

# the worker keeps the row of the file it processes locked
LOCK_TIMEOUT: str = "2s"
LOCK_NOT_AVAILABLE: str = "55P03"
STATUS_PRIORITY: tuple[MachineStatus, ...] = (
    "uploading",
    "processing",
    "failed",
    "ready",
)


@dataclass(frozen=True)
class UploadMismatch:
    """The uploaded file does not have the announced size. The CAD file is failed, its object is to delete."""

    source_key: str


def get_machine_status(statuses: Iterable[str]) -> MachineStatus:
    """The most urgent status of the machine's CAD files, ``empty`` without file."""
    ranks: list[int] = [STATUS_PRIORITY.index(stat) for stat in statuses]
    return STATUS_PRIORITY[min(ranks)] if ranks else "empty"


class CatalogService:
    def __init__(self, ograg: OgRagService, storage: ObjectStorage) -> None:
        self.ograg: OgRagService = ograg
        self.storage: ObjectStorage = storage

    async def list_machines(self, session: AsyncSession) -> list[Machine]:
        """All machines, sorted by name."""
        machines: list[Record] = await records.list_machines(self.ograg, session)
        machines.sort(key=lambda rec: _get_name(rec).casefold())
        return [await self.get_machine(session, rec.id) for rec in machines]

    async def get_machine(
        self, session: AsyncSession, machine_id: str
    ) -> MachineDetails:
        """The machine with its assembly groups and their CAD files."""
        machine: Record = await records.get_record(
            self.ograg, session, MACHINE, machine_id
        )
        groups: list[Record] = await records.list_children(
            self.ograg, session, machine_id, ASSEMBLY_GROUP
        )
        groups.sort(key=lambda rec: _get_name(rec).casefold())
        cad_files: list[CadFile] = await self._load_cad_files(
            session, await self._get_cad_files(session, groups)
        )
        return MachineDetails(
            id=machine.id,
            name=_get_name(machine),
            identifier=_get_text(machine, "identifier"),
            customer=_get_text(machine, "customer"),
            description=_get_text(machine, "description"),
            assembly_group_count=len(groups),
            cad_file_count=len(cad_files),
            status=get_machine_status(file.status for file in cad_files),
            assembly_groups=[_to_assembly_group(group, cad_files) for group in groups],
        )

    async def create_machine(
        self, session: AsyncSession, fields: Fields
    ) -> MachineDetails:
        machine_id: str = await records.create_machine(self.ograg, session, fields)
        return await self.get_machine(session, machine_id)

    async def update_machine(
        self, session: AsyncSession, machine_id: str, changes: Fields
    ) -> MachineDetails:
        await records.update_record(self.ograg, session, MACHINE, machine_id, changes)
        return await self.get_machine(session, machine_id)

    async def delete_machine(self, session: AsyncSession, machine_id: str) -> list[str]:
        """Deletes the machine, its assembly groups and their CAD files. Returns the source keys."""
        async with _busy_after_lock_timeout(session):
            # locked before their files are listed, so no file can be added meanwhile
            await self.ograg.store.lock_record(machine_id, session)
            await records.get_record(self.ograg, session, MACHINE, machine_id)
            groups: list[Record] = await records.list_children(
                self.ograg, session, machine_id, ASSEMBLY_GROUP
            )
            for group in groups:
                await self.ograg.store.lock_record(group.id, session)
            cad_files: list[Record] = await self._get_cad_files(session, groups)
            source_keys: list[str] = await _get_source_keys(session, cad_files)
            await records.delete_machine(self.ograg, session, machine_id)
        return source_keys

    async def get_assembly_group(
        self, session: AsyncSession, assembly_group_id: str
    ) -> AssemblyGroup:
        group: Record = await records.get_record(
            self.ograg, session, ASSEMBLY_GROUP, assembly_group_id
        )
        cad_files: list[CadFile] = await self._load_cad_files(
            session, await self._get_cad_files(session, [group])
        )
        return _to_assembly_group(group, cad_files)

    async def create_assembly_group(
        self, session: AsyncSession, machine_id: str, fields: Fields
    ) -> AssemblyGroup:
        group_id: str = await records.create_assembly_group(
            self.ograg, session, machine_id, fields
        )
        return await self.get_assembly_group(session, group_id)

    async def update_assembly_group(
        self, session: AsyncSession, assembly_group_id: str, changes: Fields
    ) -> AssemblyGroup:
        await records.update_record(
            self.ograg, session, ASSEMBLY_GROUP, assembly_group_id, changes
        )
        return await self.get_assembly_group(session, assembly_group_id)

    async def delete_assembly_group(
        self, session: AsyncSession, assembly_group_id: str
    ) -> list[str]:
        """Deletes the assembly group and its CAD files. Returns the source keys."""
        async with _busy_after_lock_timeout(session):
            # locked before its files are listed, so no file can be added meanwhile
            await self.ograg.store.lock_record(assembly_group_id, session)
            group: Record = await records.get_record(
                self.ograg, session, ASSEMBLY_GROUP, assembly_group_id
            )
            cad_files: list[Record] = await self._get_cad_files(session, [group])
            source_keys: list[str] = await _get_source_keys(session, cad_files)
            await records.delete_assembly_group(self.ograg, session, assembly_group_id)
        return source_keys

    async def register_cad_files(
        self,
        session: AsyncSession,
        assembly_group_id: str,
        files: list[FileToUpload],
    ) -> list[CadFileUpload]:
        """Registers CAD files, each with an upload form."""
        group: Record = await records.get_record(
            self.ograg, session, ASSEMBLY_GROUP, assembly_group_id
        )
        machine_id: str = str(group.graph[PART_OF])
        uploads: list[CadFileUpload] = []
        for file in files:
            cad_file_id: str = await records.create_cad_file(
                self.ograg, session, assembly_group_id, file.filename
            )
            source_key: str = get_source_key(machine_id, assembly_group_id, cad_file_id)
            await session.execute(
                insert(cad_uploads).values(
                    {
                        CadUploadColumn.CAD_FILE_ID: cad_file_id,
                        CadUploadColumn.SOURCE_KEY: source_key,
                        CadUploadColumn.SIZE_BYTES: file.size,
                    }
                )
            )
            url, fields = self.storage.create_upload_form(source_key, file.size)
            uploads.append(
                CadFileUpload(
                    id=cad_file_id,
                    name=file.filename,
                    upload=UploadForm(url=url, fields=fields),
                )
            )
        return uploads

    async def get_cad_file(self, session: AsyncSession, cad_file_id: str) -> CadFile:
        record: Record = await records.get_record(
            self.ograg, session, CAD_FILE, cad_file_id
        )
        return _to_cad_file(record, await _get_upload(session, cad_file_id))

    async def rename_cad_file(
        self, session: AsyncSession, cad_file_id: str, name: str
    ) -> CadFile:
        await records.update_record(
            self.ograg, session, CAD_FILE, cad_file_id, {"name": name}
        )
        return await self.get_cad_file(session, cad_file_id)

    async def complete_upload(
        self, session: AsyncSession, cad_file_id: str
    ) -> CadFile | UploadMismatch:
        """Queues the uploaded file for processing. Returns the current state once it left uploading.

        Raises:
            UploadNotFoundError: the file has not been uploaded.
            ImportFailedError: the import failed earlier.
            BusyError: the worker holds the file.
        """
        record: Record = await records.get_record(
            self.ograg, session, CAD_FILE, cad_file_id
        )
        async with _busy_after_lock_timeout(session):
            upload: Row[Any] = await _get_upload(session, cad_file_id)
            if upload.status != CadUploadStatus.UPLOADING:
                return _to_completed_cad_file(record, upload)

            size: int | None = await asyncio.to_thread(
                self.storage.get_object_size, upload.source_key
            )
            if size is None:
                # a concurrent request may have completed or failed the upload meanwhile
                upload = await _get_upload(session, cad_file_id)
                if upload.status != CadUploadStatus.UPLOADING:
                    return _to_completed_cad_file(record, upload)
                raise UploadNotFoundError()

            mismatch: bool = size != upload.size_bytes
            changed: Row[Any] | None = (
                await session.execute(
                    update(cad_uploads)
                    .where(
                        cad_uploads.c[CadUploadColumn.CAD_FILE_ID] == cad_file_id,
                        cad_uploads.c[CadUploadColumn.STATUS]
                        == CadUploadStatus.UPLOADING,
                    )
                    .values(
                        {
                            CadUploadColumn.STATUS: CadUploadStatus.FAILED
                            if mismatch
                            else CadUploadStatus.PROCESSING,
                            CadUploadColumn.ERROR_CODE: "file_mismatch"
                            if mismatch
                            else None,
                        }
                    )
                    .returning(*cad_uploads.c)
                )
            ).first()

        if changed is None:
            return _to_completed_cad_file(
                record, await _get_upload(session, cad_file_id)
            )
        if mismatch:
            return UploadMismatch(upload.source_key)
        return _to_cad_file(record, changed)

    async def delete_cad_file(
        self, session: AsyncSession, cad_file_id: str
    ) -> list[str]:
        """Deletes the CAD file. Returns its source key."""
        async with _busy_after_lock_timeout(session):
            record: Record = await records.get_record(
                self.ograg, session, CAD_FILE, cad_file_id
            )
            source_keys: list[str] = await _get_source_keys(session, [record])
            await records.delete_cad_file(self.ograg, session, cad_file_id)
        return source_keys

    def delete_source_folders(self, source_keys: list[str]) -> None:
        """Deletes the folder of each source key. Blocking, call it after the commit."""
        self.storage.delete_folders_quietly([get_folder(key) for key in source_keys])

    async def _get_cad_files(
        self, session: AsyncSession, groups: list[Record]
    ) -> list[Record]:
        if not groups:
            return []
        linking: list[Record] = await self.ograg.store.get_linking_records(
            [group.id for group in groups], session
        )
        return [rec for rec in linking if rec.cls == CAD_FILE]

    async def _load_cad_files(
        self, session: AsyncSession, cad_files: list[Record]
    ) -> list[CadFile]:
        """The CAD files with their upload state, oldest first."""
        if not cad_files:
            return []
        rows: Result[Any] = await session.execute(
            select(cad_uploads).where(
                cad_uploads.c[CadUploadColumn.CAD_FILE_ID].in_(
                    [rec.id for rec in cad_files]
                )
            )
        )
        uploads: dict[str, Row[Any]] = {row.cad_file_id: row for row in rows}
        # a file deleted between the two queries has no upload row any more
        loaded: list[CadFile] = [
            _to_cad_file(rec, uploads[rec.id]) for rec in cad_files if rec.id in uploads
        ]
        return sorted(loaded, key=lambda file: file.created_at)


@asynccontextmanager
async def _busy_after_lock_timeout(session: AsyncSession) -> AsyncIterator[None]:
    """Waits at most ``LOCK_TIMEOUT`` for a locked row, then raises ``BusyError`` instead of waiting for the worker."""
    await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    try:
        yield
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) != LOCK_NOT_AVAILABLE:
            raise
        raise BusyError() from exc


async def _get_upload(session: AsyncSession, cad_file_id: str) -> Row[Any]:
    upload: Row[Any] | None = (
        await session.execute(
            select(cad_uploads).where(
                cad_uploads.c[CadUploadColumn.CAD_FILE_ID] == cad_file_id
            )
        )
    ).first()
    if upload is None:
        raise NotFoundError(ERROR_NOT_FOUND.format(cls=CAD_FILE, record_id=cad_file_id))
    return upload


async def _get_source_keys(session: AsyncSession, cad_files: list[Record]) -> list[str]:
    if not cad_files:
        return []
    rows: Result[Any] = await session.execute(
        select(cad_uploads.c[CadUploadColumn.SOURCE_KEY]).where(
            cad_uploads.c[CadUploadColumn.CAD_FILE_ID].in_(
                [rec.id for rec in cad_files]
            )
        )
    )
    return list(rows.scalars())


def _to_completed_cad_file(record: Record, upload: Row[Any]) -> CadFile:
    if upload.status == CadUploadStatus.FAILED:
        raise ImportFailedError(upload.error_code)
    return _to_cad_file(record, upload)


def _to_cad_file(record: Record, upload: Row[Any]) -> CadFile:
    return CadFile(
        id=record.id,
        name=_get_name(record),
        assembly_group_id=str(record.graph[PART_OF]),
        status=upload.status,
        error_code=upload.error_code,
        size_bytes=upload.size_bytes,
        created_at=upload.created_at,
        updated_at=upload.updated_at,
    )


def _to_assembly_group(group: Record, cad_files: list[CadFile]) -> AssemblyGroup:
    return AssemblyGroup(
        id=group.id,
        machine_id=str(group.graph[PART_OF]),
        name=_get_name(group),
        identifier=_get_text(group, "identifier"),
        description=_get_text(group, "description"),
        cad_files=[file for file in cad_files if file.assembly_group_id == group.id],
    )


def _get_name(record: Record) -> str:
    return str(record.graph["name"])


def _get_text(record: Record, field: str) -> str | None:
    value: Json = record.graph.get(field)
    return None if value is None else str(value)
