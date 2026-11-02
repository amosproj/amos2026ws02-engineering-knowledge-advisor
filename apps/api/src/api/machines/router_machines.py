from typing import Annotated
from uuid import UUID, uuid4

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from api.router_builder import ApiRouterBuilder
from db import Machine, MachineStatus, get_session
from logger import logger
from model.machine import (
    CreateMachineRequest,
    CreateMachineResponse,
    MachineResponse,
    UploadForm,
)
from model.problem import Problem, ProblemException
from storage.s3 import create_upload_form, delete_object, get_object_size

machines_router: APIRouter = (
    ApiRouterBuilder().version("v1").add_tags(["machines"]).build()
)


@machines_router.post(
    "/machines",
    status_code=status.HTTP_201_CREATED,
    responses={
        422: {"model": Problem, "description": "Request body validation error"},
        500: {"model": Problem, "description": "Internal server error"},
    },
)
def create_machine(
    body: CreateMachineRequest,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> CreateMachineResponse:
    """Register a machine and return a form to upload its STEP file to storage."""
    machine_id = uuid4()
    machine = Machine(
        id=machine_id,
        name=body.name,
        description=body.description,
        object_key=f"machines/{machine_id}/source.step",
        original_filename=body.filename,
        size_bytes=body.size,
    )
    url, fields = create_upload_form(machine.object_key, body.size)
    session.add(machine)
    session.commit()

    response.headers["Location"] = f"{machines_router.prefix}/machines/{machine_id}"
    return CreateMachineResponse(
        id=machine_id, upload=UploadForm(url=url, fields=fields)
    )


@machines_router.get(
    "/machines/{machine_id}",
    responses={
        404: {"model": Problem, "description": "Machine not found"},
        422: {"model": Problem, "description": "Invalid machine id"},
    },
)
def get_machine(
    machine_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> MachineResponse:
    """Return the import state of a machine."""
    return MachineResponse.model_validate(_find_machine(session, machine_id))


@machines_router.post(
    "/machines/{machine_id}/complete",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        404: {"model": Problem, "description": "Machine not found"},
        409: {"model": Problem, "description": "Upload missing or import failed"},
        422: {"model": Problem, "description": "Invalid machine id"},
        500: {"model": Problem, "description": "Internal server error"},
    },
)
def complete_machine_upload(
    machine_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> MachineResponse:
    """Confirm that the STEP file was uploaded and start processing it."""
    machine = _find_machine(session, machine_id)
    if machine.status != MachineStatus.UPLOADING:
        return _accepted_state(machine)

    object_key, expected_size = machine.object_key, machine.size_bytes
    session.rollback()

    size = get_object_size(object_key)
    if size is None:
        # A concurrent request may have failed the import and deleted the object
        machine = _find_machine(session, machine_id)
        if machine.status != MachineStatus.UPLOADING:
            return _accepted_state(machine)
        raise ProblemException(
            Problem.from_status(
                409,
                "The STEP file has not been uploaded",
                error_code="upload_not_found",
            )
        )

    if size != expected_size:
        if _leave_uploading(session, machine_id, MachineStatus.FAILED, "file_mismatch"):
            _delete_object_quietly(object_key)
    else:
        _leave_uploading(session, machine_id, MachineStatus.PROCESSING)

    return _accepted_state(_find_machine(session, machine_id))


def _find_machine(session: Session, machine_id: UUID) -> Machine:
    machine = session.get(Machine, machine_id)
    if machine is None:
        raise ProblemException(Problem.from_status(404, "Machine not found"))
    return machine


def _accepted_state(machine: Machine) -> MachineResponse:
    if machine.status == MachineStatus.FAILED:
        raise ProblemException(
            Problem.from_status(
                409, "The machine import failed", error_code=machine.error_code
            )
        )
    return MachineResponse.model_validate(machine)


def _leave_uploading(
    session: Session,
    machine_id: UUID,
    new_status: MachineStatus,
    error_code: str | None = None,
) -> bool:
    """Move the machine out of uploading. False if a concurrent request already did."""
    updated = session.execute(
        update(Machine)
        .where(Machine.id == machine_id, Machine.status == MachineStatus.UPLOADING)
        .values(status=new_status, error_code=error_code)
        .returning(Machine.id)
    ).scalar_one_or_none()
    session.commit()
    return updated is not None


def _delete_object_quietly(object_key: str) -> None:
    try:
        delete_object(object_key)
    except (BotoCoreError, ClientError):
        logger.exception(f"Could not delete object {object_key}")
