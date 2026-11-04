from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status

from api.router_builder import ApiRouterBuilder
from api.router_records import RecordId, Session
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
    UploadRequest,
)
from model.problem import Problem, ProblemResponse
from services.catalog import CatalogService, UploadMismatch

RESPONSE_DETAIL_404: str = "No such machine, assembly group or CAD file."
RESPONSE_DETAIL_409_BUSY: str = "A CAD file is being processed. Please try again."
RESPONSE_DETAIL_409_COMPLETE: str = "Upload not found, file does not match or import failed (see error_code), or the file is being processed."
RESPONSE_DETAIL_422: str = "Request validation failed."
ERROR_FILE_MISMATCH: str = "The uploaded file does not match the announced size."

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

v1_catalog_router: APIRouter = (
    ApiRouterBuilder().version("v1").add_tags(["catalog"]).build()
)


def get_catalog(request: Request) -> CatalogService:
    return request.app.state.catalog


Catalog = Annotated[CatalogService, Depends(get_catalog)]


@v1_catalog_router.post(
    "/machines",
    status_code=status.HTTP_201_CREATED,
    responses=INVALID,
)
async def post_machine(
    body: MachineFields, catalog: Catalog, session: Session
) -> Machine:
    return await catalog.create_machine(session, body.model_dump())


@v1_catalog_router.get("/machines")
async def get_machines(catalog: Catalog, session: Session) -> list[Machine]:
    """All machines, sorted by name."""
    return await catalog.list_machines(session)


@v1_catalog_router.get("/machines/{machine_id}", responses=NOT_FOUND)
async def get_machine(
    machine_id: RecordId, catalog: Catalog, session: Session
) -> MachineDetails:
    """The machine with its assembly groups and their CAD files."""
    return await catalog.get_machine(session, machine_id)


@v1_catalog_router.patch("/machines/{machine_id}", responses=NOT_FOUND)
async def patch_machine(
    machine_id: RecordId, body: MachineChanges, catalog: Catalog, session: Session
) -> Machine:
    """Changes the fields sent. ``null`` or blank clears an optional field."""
    return await catalog.update_machine(
        session, machine_id, body.model_dump(exclude_unset=True)
    )


@v1_catalog_router.delete(
    "/machines/{machine_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**NOT_FOUND, **BUSY},
)
async def delete_machine_route(
    machine_id: RecordId,
    catalog: Catalog,
    session: Session,
    background_tasks: BackgroundTasks,
) -> None:
    """Deletes the machine, its assembly groups and their CAD files. Cancels their uploads."""
    source_keys: list[str] = await catalog.delete_machine(session, machine_id)
    background_tasks.add_task(catalog.delete_source_folders, source_keys)


@v1_catalog_router.post(
    "/machines/{machine_id}/assembly-groups",
    status_code=status.HTTP_201_CREATED,
    responses=NOT_FOUND,
)
async def post_assembly_group(
    machine_id: RecordId,
    body: AssemblyGroupFields,
    catalog: Catalog,
    session: Session,
) -> AssemblyGroup:
    return await catalog.create_assembly_group(session, machine_id, body.model_dump())


@v1_catalog_router.get("/assembly-groups/{assembly_group_id}", responses=NOT_FOUND)
async def get_assembly_group(
    assembly_group_id: RecordId, catalog: Catalog, session: Session
) -> AssemblyGroup:
    return await catalog.get_assembly_group(session, assembly_group_id)


@v1_catalog_router.patch(
    "/assembly-groups/{assembly_group_id}",
    responses=NOT_FOUND,
)
async def patch_assembly_group(
    assembly_group_id: RecordId,
    body: AssemblyGroupChanges,
    catalog: Catalog,
    session: Session,
) -> AssemblyGroup:
    """Changes the fields sent. ``null`` or blank clears an optional field."""
    return await catalog.update_assembly_group(
        session, assembly_group_id, body.model_dump(exclude_unset=True)
    )


@v1_catalog_router.delete(
    "/assembly-groups/{assembly_group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**NOT_FOUND, **BUSY},
)
async def delete_assembly_group_route(
    assembly_group_id: RecordId,
    catalog: Catalog,
    session: Session,
    background_tasks: BackgroundTasks,
) -> None:
    """Deletes the assembly group and its CAD files. Cancels their uploads."""
    source_keys: list[str] = await catalog.delete_assembly_group(
        session, assembly_group_id
    )
    background_tasks.add_task(catalog.delete_source_folders, source_keys)


@v1_catalog_router.post(
    "/assembly-groups/{assembly_group_id}/cad-files",
    status_code=status.HTTP_201_CREATED,
    responses=NOT_FOUND,
)
async def post_cad_files(
    assembly_group_id: RecordId,
    body: UploadRequest,
    catalog: Catalog,
    session: Session,
) -> list[CadFileUpload]:
    """Registers CAD files and returns one upload form each.

    Upload each file with its form, then call ``POST /cad-files/{id}/complete``.
    """
    return await catalog.register_cad_files(session, assembly_group_id, body.files)


@v1_catalog_router.get("/cad-files/{cad_file_id}", responses=NOT_FOUND)
async def get_cad_file(
    cad_file_id: RecordId, catalog: Catalog, session: Session
) -> CadFile:
    return await catalog.get_cad_file(session, cad_file_id)


@v1_catalog_router.patch("/cad-files/{cad_file_id}", responses=NOT_FOUND)
async def patch_cad_file(
    cad_file_id: RecordId, body: CadFileChanges, catalog: Catalog, session: Session
) -> CadFile:
    """Renames the CAD file."""
    return await catalog.rename_cad_file(session, cad_file_id, body.name)


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
    catalog: Catalog,
    session: Session,
    background_tasks: BackgroundTasks,
) -> CadFile | Response:
    """Confirms that the file was uploaded and queues it for processing."""
    result: CadFile | UploadMismatch = await catalog.complete_upload(
        session, cad_file_id
    )
    if isinstance(result, UploadMismatch):
        background_tasks.add_task(catalog.delete_source_folders, [result.source_key])
        # returned, not raised: raising would roll back the failed status
        return ProblemResponse.from_status(
            409,
            ERROR_FILE_MISMATCH,
            error_code="file_mismatch",
            instance=request.url.path,
        )
    return result


@v1_catalog_router.delete(
    "/cad-files/{cad_file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**NOT_FOUND, **BUSY},
)
async def delete_cad_file_route(
    cad_file_id: RecordId,
    catalog: Catalog,
    session: Session,
    background_tasks: BackgroundTasks,
) -> None:
    """Deletes the CAD file. Cancels its upload."""
    source_keys: list[str] = await catalog.delete_cad_file(session, cad_file_id)
    background_tasks.add_task(catalog.delete_source_folders, source_keys)
