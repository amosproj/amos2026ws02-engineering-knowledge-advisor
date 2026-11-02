from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from api.router_builder import ApiRouterBuilder
from db import Machine, get_session
from model.machine import CreateMachineRequest, CreateMachineResponse, UploadForm
from model.problem import Problem
from storage.s3 import create_upload_form

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
