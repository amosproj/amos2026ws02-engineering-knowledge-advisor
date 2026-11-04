from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from services import JsonObject
from services.ograg.ontology import JSONLD_ID, JSONLD_TYPE

STEP_FILE_MAX_SIZE: int = 5 * 1024 * 1024 * 1024  # 5 GiB
MAX_FILES_PER_UPLOAD: int = 5

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]
ShortText = Annotated[
    str | None, StringConstraints(strip_whitespace=True, max_length=255)
]
Description = Annotated[
    str | None, StringConstraints(strip_whitespace=True, max_length=1000)
]
StepFileName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, max_length=255, pattern=r"(?i)^.+\.(stp|step)$"
    ),
]


class TestRequest(BaseModel):
    ping: int


class RecordNode(BaseModel):
    """JSON-LD node of a record class. Properties as defined by the ontology. Links hold target ids.
    Every property besides ``@type`` and ``@id`` is kept as sent.
    """

    model_config = ConfigDict(extra="allow")

    type: str | None = Field(
        default=None,
        alias=JSONLD_TYPE,
        description="Record class. Defaults to anchor class.",
    )
    id: str | None = Field(
        default=None,
        alias=JSONLD_ID,
        description="Record id. PUT specifies it in the URL.",
    )

    def to_node(self) -> JsonObject:
        """Returns the node as sent."""
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")


class MachineFields(BaseModel):
    name: Name
    identifier: ShortText = None
    customer: ShortText = None
    description: Description = None


class MachineChanges(BaseModel):
    """Fields left out stay unchanged; null or blank clears an optional field."""

    name: Name | None = None
    identifier: ShortText = None
    customer: ShortText = None
    description: Description = None


class AssemblyGroupFields(BaseModel):
    name: Name
    identifier: ShortText = None
    description: Description = None


class AssemblyGroupChanges(BaseModel):
    """Fields left out stay unchanged; null or blank clears an optional field."""

    name: Name | None = None
    identifier: ShortText = None
    description: Description = None


class CadFileChanges(BaseModel):
    name: Name


class FileToUpload(BaseModel):
    filename: StepFileName
    size: Annotated[int, Field(ge=1, le=STEP_FILE_MAX_SIZE)]


class UploadRequest(BaseModel):
    files: Annotated[
        list[FileToUpload], Field(min_length=1, max_length=MAX_FILES_PER_UPLOAD)
    ]
