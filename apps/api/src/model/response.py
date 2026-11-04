from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, RootModel

from db import CadUploadStatus
from model.request import RecordNode

MachineStatus = Literal["empty", "uploading", "processing", "failed", "ready"]


class TestResponse(BaseModel):
    pong: int


class RecordWritten(BaseModel):
    """Response of ``PUT /records/{id}``.

    Attributes:
        warnings: validation drops
    """

    id: str
    warnings: list[str]


class RecordsDeleted(BaseModel):
    """Response of ``DELETE /records/{id}``.

    Attributes:
        deleted_ids: id of deleted record + ids of deleted orphans
        marked_ids: ids of records that lost their last parent link and were marked for review
    """

    deleted_ids: list[str]
    marked_ids: list[str]


class RecordToReview(BaseModel):
    """A marked record."""

    id: str
    review: str
    record: RecordNode


class Records(RootModel[dict[str, RecordNode]]):
    """Response of ``GET /records``. Wraps map: record id -> validated node"""


class UploadForm(BaseModel):
    """Presigned POST form: send ``fields`` and then the file as ``file`` to ``url``."""

    url: str
    fields: dict[str, str]


class CadFileUpload(BaseModel):
    id: str
    name: str
    upload: UploadForm


class CadFile(BaseModel):
    id: str
    name: str
    assembly_group_id: str
    status: CadUploadStatus
    error_code: str | None
    size_bytes: int
    created_at: datetime
    updated_at: datetime


class AssemblyGroup(BaseModel):
    id: str
    machine_id: str
    name: str
    identifier: str | None
    description: str | None
    cad_files: list[CadFile]


class Machine(BaseModel):
    id: str
    name: str
    identifier: str | None
    customer: str | None
    description: str | None
    assembly_group_count: int
    cad_file_count: int
    status: MachineStatus = Field(
        description="Most urgent status of its CAD files: uploading, processing, failed, ready. empty without file."
    )


class MachineDetails(Machine):
    assembly_groups: list[AssemblyGroup]
