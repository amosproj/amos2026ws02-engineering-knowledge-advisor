from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_validator

STEP_FILE_MAX_SIZE = 5 * 1024 * 1024 * 1024 # 5 GB


class CreateMachineRequest(BaseModel):
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ]
    description: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=1000)
    ] = None
    filename: Annotated[
        str, StringConstraints(max_length=255, pattern=r"(?i)\.(stp|step)$")
    ]
    size: Annotated[int, Field(ge=1, le=STEP_FILE_MAX_SIZE)]

    @field_validator("description")
    @classmethod
    def _empty_description_to_none(cls, value: str | None) -> str | None:
        return value or None


class UploadForm(BaseModel):
    url: str
    fields: dict[str, str]


class CreateMachineResponse(BaseModel):
    id: UUID
    upload: UploadForm
