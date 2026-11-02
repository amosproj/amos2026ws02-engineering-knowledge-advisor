from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from db import MachineStatus

STEP_FILE_MAX_SIZE = 5 * 1024 * 1024 * 1024  # 5 GB


class MachineDetails(BaseModel):
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ]
    description: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=1000)
    ] = None

    @field_validator("description")
    @classmethod
    def _empty_description_to_none(cls, value: str | None) -> str | None:
        return value or None


class CreateMachineRequest(MachineDetails):
    filename: Annotated[
        str, StringConstraints(max_length=255, pattern=r"(?i)\.(stp|step)$")
    ]
    size: Annotated[int, Field(ge=1, le=STEP_FILE_MAX_SIZE)]


class UploadForm(BaseModel):
    url: str
    fields: dict[str, str]


class CreateMachineResponse(BaseModel):
    id: UUID
    upload: UploadForm


class MachineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    status: MachineStatus
    error_code: str | None
    original_filename: str
    size_bytes: int
    created_at: datetime
    updated_at: datetime
