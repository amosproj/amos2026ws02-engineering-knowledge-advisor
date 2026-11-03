import asyncio
import posixpath
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, BackgroundTasks, Request, Response, status
from sqlalchemy import Row, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.router_builder import ApiRouterBuilder
from api.router_records import RecordId, Service, Session
from db import CadUploadStatus, cad_uploads
from logger import logger
from model import (
    AssemblyGroup,
    AssemblyGroupChanges,
    AssemblyGroupFields,
    CadFile,
    CadFileChanges,
    CadFileUpload,
    Machine,
    MachineChanges,
    MachineDetails,
    MachineFields,
    MachineStatus,
    UploadForm,
    UploadRequest,
)
from model.problem import Problem, ProblemException, ProblemResponse
from services import Record
from services.catalog import (
    ASSEMBLY_GROUP,
    CAD_FILE,
    MACHINE,
    PART_OF,
    create_assembly_group,
    create_cad_file,
    create_machine,
    delete_assembly_group,
    delete_cad_file,
    delete_machine,
    get_record,
    list_children,
    list_machines,
    update_record,
)
from services.ograg.service import OgRagService
from storage.s3 import (
    SOURCE_FILE_NAME,
    cad_file_folder,
    create_upload_form,
    delete_folder,
    delete_object_quietly,
    get_object_size,
)

# the worker keeps the row of the file it processes locked
LOCK_TIMEOUT: str = "2s"
LOCK_NOT_AVAILABLE: str = "55P03"
STATUS_PRIORITY: tuple[MachineStatus, ...] = (
    "uploading",
    "processing",
    "failed",
    "ready",
)

RESPONSE_DETAIL_404: str = "No such machine, assembly group or CAD file."
RESPONSE_DETAIL_409_BUSY: str = "A CAD file is being processed. Please try again."
RESPONSE_DETAIL_409_IDENTIFIER: str = "Identifier already used."
RESPONSE_DETAIL_409_COMPLETE: str = "Upload not found, file does not match or import failed (see error_code), or the file is being processed."
RESPONSE_DETAIL_422: str = "Request validation failed."
ERROR_UPLOAD_NOT_FOUND: str = "The CAD file has not been uploaded."
ERROR_FILE_MISMATCH: str = "The uploaded file does not match the announced size."
ERROR_IMPORT_FAILED: str = "The CAD file import failed."
LOG_DELETE_FAILED: str = "Could not delete the folder of {key}"

INVALID: dict[int | str, dict[str, Any]] = {
    422: {"model": Problem, "description": RESPONSE_DETAIL_422},
}
NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": Problem, "description": RESPONSE_DETAIL_404},
    **INVALID,
}
BUSY: dict[int | str, dict[str, Any]] = {
    409: {"model": Problem, "description": RESPONSE_DETAIL_409_BUSY},
}
IDENTIFIER_TAKEN: dict[int | str, dict[str, Any]] = {
    409: {"model": Problem, "description": RESPONSE_DETAIL_409_IDENTIFIER},
}

v1_catalog_router: APIRouter = (
    ApiRouterBuilder().version("v1").add_tags(["catalog"]).build()
)


@v1_catalog_router.post(
    "/machines",
    status_code=status.HTTP_201_CREATED,
    responses={**INVALID, **IDENTIFIER_TAKEN},
)
async def post_machine(
    body: MachineFields, service: Service, session: Session
) -> Machine:
    machine_id: str = await create_machine(service, session, body.model_dump())
    return await _load_machine(service, session, machine_id)


@v1_catalog_router.get("/machines")
async def get_machines(service: Service, session: Session) -> list[Machine]:
    """All machines, sorted by name."""
    machines: list[Record] = await list_machines(service, session)
    machines.sort(key=lambda rec: _get_name(rec).casefold())
    return [await _load_machine(service, session, rec.id) for rec in machines]


@v1_catalog_router.get("/machines/{machine_id}", responses=NOT_FOUND)
async def get_machine(
    machine_id: RecordId, service: Service, session: Session
) -> MachineDetails:
    """The machine with its assembly groups and their CAD files."""
    return await _load_machine(service, session, machine_id)


@v1_catalog_router.patch(
    "/machines/{machine_id}", responses={**NOT_FOUND, **IDENTIFIER_TAKEN}
)
async def patch_machine(
    machine_id: RecordId, body: MachineChanges, service: Service, session: Session
) -> Machine:
    """Changes the fields sent. ``null`` or blank clears an optional field."""
    changes = body.model_dump(exclude_unset=True)
    await update_record(service, session, MACHINE, machine_id, changes)
    return await _load_machine(service, session, machine_id)


@v1_catalog_router.delete(
    "/machines/{machine_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**NOT_FOUND, **BUSY},
)
async def delete_machine_route(
    machine_id: RecordId,
    service: Service,
    session: Session,
    background_tasks: BackgroundTasks,
) -> None:
    """Deletes the machine, its assembly groups and their CAD files. Cancels their uploads."""
    async with _answer_409_when_busy(session):
        # locked before their files are listed, so no file can be added meanwhile
        await service.store.lock_record(machine_id, session)
        await get_record(service, session, MACHINE, machine_id)
        groups: list[Record] = await list_children(
            service, session, machine_id, ASSEMBLY_GROUP
        )
        for group in groups:
            await service.store.lock_record(group.id, session)
        cad_files: list[Record] = await _get_cad_files(service, session, groups)
        source_keys: list[str] = await _get_source_keys(session, cad_files)
        await delete_machine(service, session, machine_id)
    background_tasks.add_task(_delete_source_folders, source_keys)


@v1_catalog_router.post(
    "/machines/{machine_id}/assembly-groups",
    status_code=status.HTTP_201_CREATED,
    responses={**NOT_FOUND, **IDENTIFIER_TAKEN},
)
async def post_assembly_group(
    machine_id: RecordId,
    body: AssemblyGroupFields,
    service: Service,
    session: Session,
) -> AssemblyGroup:
    group_id: str = await create_assembly_group(
        service, session, machine_id, body.model_dump()
    )
    return await _load_assembly_group(service, session, group_id)


@v1_catalog_router.get("/assembly-groups/{assembly_group_id}", responses=NOT_FOUND)
async def get_assembly_group(
    assembly_group_id: RecordId, service: Service, session: Session
) -> AssemblyGroup:
    return await _load_assembly_group(service, session, assembly_group_id)


@v1_catalog_router.patch(
    "/assembly-groups/{assembly_group_id}",
    responses={**NOT_FOUND, **IDENTIFIER_TAKEN},
)
async def patch_assembly_group(
    assembly_group_id: RecordId,
    body: AssemblyGroupChanges,
    service: Service,
    session: Session,
) -> AssemblyGroup:
    """Changes the fields sent. ``null`` or blank clears an optional field."""
    changes = body.model_dump(exclude_unset=True)
    await update_record(service, session, ASSEMBLY_GROUP, assembly_group_id, changes)
    return await _load_assembly_group(service, session, assembly_group_id)


@v1_catalog_router.delete(
    "/assembly-groups/{assembly_group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**NOT_FOUND, **BUSY},
)
async def delete_assembly_group_route(
    assembly_group_id: RecordId,
    service: Service,
    session: Session,
    background_tasks: BackgroundTasks,
) -> None:
    """Deletes the assembly group and its CAD files. Cancels their uploads."""
    async with _answer_409_when_busy(session):
        # locked before its files are listed, so no file can be added meanwhile
        await service.store.lock_record(assembly_group_id, session)
        group: Record = await get_record(
            service, session, ASSEMBLY_GROUP, assembly_group_id
        )
        cad_files: list[Record] = await _get_cad_files(service, session, [group])
        source_keys: list[str] = await _get_source_keys(session, cad_files)
        await delete_assembly_group(service, session, assembly_group_id)
    background_tasks.add_task(_delete_source_folders, source_keys)


@v1_catalog_router.post(
    "/assembly-groups/{assembly_group_id}/cad-files",
    status_code=status.HTTP_201_CREATED,
    responses=NOT_FOUND,
)
async def post_cad_files(
    assembly_group_id: RecordId,
    body: UploadRequest,
    service: Service,
    session: Session,
) -> list[CadFileUpload]:
    """Registers CAD files and returns one upload form each.

    Upload each file with its form, then call ``POST /cad-files/{id}/complete``.
    """
    group: Record = await get_record(
        service, session, ASSEMBLY_GROUP, assembly_group_id
    )
    machine_id: str = str(group.graph[PART_OF])
    uploads: list[CadFileUpload] = []
    for file in body.files:
        cad_file_id: str = await create_cad_file(
            service, session, assembly_group_id, file.filename
        )
        source_key: str = (
            cad_file_folder(machine_id, assembly_group_id, cad_file_id)
            + SOURCE_FILE_NAME
        )
        await session.execute(
            insert(cad_uploads).values(
                cad_file_id=cad_file_id, source_key=source_key, size_bytes=file.size
            )
        )
        url, fields = create_upload_form(source_key, file.size)
        uploads.append(
            CadFileUpload(
                id=cad_file_id,
                name=file.filename,
                upload=UploadForm(url=url, fields=fields),
            )
        )
    return uploads


@v1_catalog_router.get("/cad-files/{cad_file_id}", responses=NOT_FOUND)
async def get_cad_file(
    cad_file_id: RecordId, service: Service, session: Session
) -> CadFile:
    record: Record = await get_record(service, session, CAD_FILE, cad_file_id)
    return _to_cad_file(record, await _get_upload(session, cad_file_id))


@v1_catalog_router.patch("/cad-files/{cad_file_id}", responses=NOT_FOUND)
async def patch_cad_file(
    cad_file_id: RecordId, body: CadFileChanges, service: Service, session: Session
) -> CadFile:
    """Renames the CAD file."""
    await update_record(service, session, CAD_FILE, cad_file_id, {"name": body.name})
    record: Record = await get_record(service, session, CAD_FILE, cad_file_id)
    return _to_cad_file(record, await _get_upload(session, cad_file_id))


@v1_catalog_router.post(
    "/cad-files/{cad_file_id}/complete",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CadFile,
    responses={
        **NOT_FOUND,
        409: {"model": Problem, "description": RESPONSE_DETAIL_409_COMPLETE},
    },
)
async def complete_cad_file_upload(
    cad_file_id: RecordId,
    request: Request,
    service: Service,
    session: Session,
    background_tasks: BackgroundTasks,
) -> CadFile | Response:
    """Confirms that the file was uploaded and queues it for processing."""
    record: Record = await get_record(service, session, CAD_FILE, cad_file_id)
    async with _answer_409_when_busy(session):
        upload: Row[Any] = await _get_upload(session, cad_file_id)
        if upload.status != CadUploadStatus.UPLOADING:
            return _to_completed_cad_file(record, upload)

        size: int | None = await asyncio.to_thread(get_object_size, upload.source_key)
        if size is None:
            # a concurrent request may have completed or failed the upload meanwhile
            upload = await _get_upload(session, cad_file_id)
            if upload.status != CadUploadStatus.UPLOADING:
                return _to_completed_cad_file(record, upload)
            raise ProblemException(
                Problem.from_status(
                    409, ERROR_UPLOAD_NOT_FOUND, error_code="upload_not_found"
                )
            )

        mismatch: bool = size != upload.size_bytes
        changed: Row[Any] | None = (
            await session.execute(
                update(cad_uploads)
                .where(
                    cad_uploads.c.cad_file_id == cad_file_id,
                    cad_uploads.c.status == CadUploadStatus.UPLOADING,
                )
                .values(
                    status=CadUploadStatus.FAILED
                    if mismatch
                    else CadUploadStatus.PROCESSING,
                    error_code="file_mismatch" if mismatch else None,
                )
                .returning(*cad_uploads.c)
            )
        ).first()

    if changed is None:
        return _to_completed_cad_file(record, await _get_upload(session, cad_file_id))
    if mismatch:
        background_tasks.add_task(delete_object_quietly, upload.source_key)
        # returned, not raised: raising would roll back the failed status
        return ProblemResponse.from_status(
            409,
            ERROR_FILE_MISMATCH,
            error_code="file_mismatch",
            instance=request.url.path,
        )
    return _to_cad_file(record, changed)


@v1_catalog_router.delete(
    "/cad-files/{cad_file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**NOT_FOUND, **BUSY},
)
async def delete_cad_file_route(
    cad_file_id: RecordId,
    service: Service,
    session: Session,
    background_tasks: BackgroundTasks,
) -> None:
    """Deletes the CAD file. Cancels its upload."""
    async with _answer_409_when_busy(session):
        record: Record = await get_record(service, session, CAD_FILE, cad_file_id)
        source_keys: list[str] = await _get_source_keys(session, [record])
        await delete_cad_file(service, session, cad_file_id)
    background_tasks.add_task(_delete_source_folders, source_keys)


def get_machine_status(statuses: Iterable[str]) -> MachineStatus:
    """The most urgent status of the machine's CAD files, ``empty`` without file."""
    ranks: list[int] = [STATUS_PRIORITY.index(stat) for stat in statuses]
    return STATUS_PRIORITY[min(ranks)] if ranks else "empty"


@asynccontextmanager
async def _answer_409_when_busy(session: AsyncSession) -> AsyncIterator[None]:
    """Waits at most ``LOCK_TIMEOUT`` for a locked row, then answers 409 instead of waiting for the worker."""
    await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    try:
        yield
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) != LOCK_NOT_AVAILABLE:
            raise
        raise ProblemException(
            Problem.from_status(409, RESPONSE_DETAIL_409_BUSY)
        ) from exc


async def _load_machine(
    service: OgRagService, session: AsyncSession, machine_id: str
) -> MachineDetails:
    machine: Record = await get_record(service, session, MACHINE, machine_id)
    groups: list[Record] = await list_children(
        service, session, machine_id, ASSEMBLY_GROUP
    )
    groups.sort(key=lambda rec: _get_name(rec).casefold())
    cad_files: list[CadFile] = await _load_cad_files(
        session, await _get_cad_files(service, session, groups)
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


async def _load_assembly_group(
    service: OgRagService, session: AsyncSession, assembly_group_id: str
) -> AssemblyGroup:
    group: Record = await get_record(
        service, session, ASSEMBLY_GROUP, assembly_group_id
    )
    cad_files: list[CadFile] = await _load_cad_files(
        session, await _get_cad_files(service, session, [group])
    )
    return _to_assembly_group(group, cad_files)


async def _get_cad_files(
    service: OgRagService, session: AsyncSession, groups: list[Record]
) -> list[Record]:
    if not groups:
        return []
    linking: list[Record] = await service.store.get_linking_records(
        [group.id for group in groups], session
    )
    return [rec for rec in linking if rec.cls == CAD_FILE]


async def _load_cad_files(
    session: AsyncSession, records: list[Record]
) -> list[CadFile]:
    """The CAD files with their upload state, oldest first."""
    if not records:
        return []
    rows = await session.execute(
        select(cad_uploads).where(
            cad_uploads.c.cad_file_id.in_([rec.id for rec in records])
        )
    )
    uploads: dict[str, Row[Any]] = {row.cad_file_id: row for row in rows}
    # a file deleted between the two queries has no upload row any more
    cad_files: list[CadFile] = [
        _to_cad_file(rec, uploads[rec.id]) for rec in records if rec.id in uploads
    ]
    return sorted(cad_files, key=lambda file: file.created_at)


async def _get_upload(session: AsyncSession, cad_file_id: str) -> Row[Any]:
    upload: Row[Any] | None = (
        await session.execute(
            select(cad_uploads).where(cad_uploads.c.cad_file_id == cad_file_id)
        )
    ).first()
    if upload is None:
        raise ProblemException(Problem.from_status(404, RESPONSE_DETAIL_404))
    return upload


async def _get_source_keys(session: AsyncSession, cad_files: list[Record]) -> list[str]:
    if not cad_files:
        return []
    rows = await session.execute(
        select(cad_uploads.c.source_key).where(
            cad_uploads.c.cad_file_id.in_([rec.id for rec in cad_files])
        )
    )
    return list(rows.scalars())


def _delete_source_folders(source_keys: list[str]) -> None:
    """Deletes the folder of each file, with its source and anything derived from it."""
    for key in source_keys:
        try:
            delete_folder(posixpath.dirname(key) + "/")
        except (BotoCoreError, ClientError):
            # the worker deletes the objects left without a file later
            logger.exception(LOG_DELETE_FAILED.format(key=key))


def _to_completed_cad_file(record: Record, upload: Row[Any]) -> CadFile:
    if upload.status == CadUploadStatus.FAILED:
        raise ProblemException(
            Problem.from_status(409, ERROR_IMPORT_FAILED, error_code=upload.error_code)
        )
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
    value = record.graph.get(field)
    return None if value is None else str(value)
