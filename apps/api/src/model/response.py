from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, RootModel

from model.request import CamelModel, RecordNode
from services.ograg.ontology import EdgeType
from services.search import SearchMode
from services.uploads import UploadStatus

NO_FILE: Literal["empty"] = "empty"

FileStatus = UploadStatus | Literal["empty"]

FIELD_DESCRIPTION_UPLOAD: str = "Upload of a file record: status, size, error code and times. Null before the first upload."
FIELD_DESCRIPTION_VERSION: str = (
    "Changes on every save. Send as If-Match with PUT, PATCH or DELETE."
)


class RecordWritten(CamelModel):
    """Response of ``POST /records``, ``PUT /records/{id}`` and ``PATCH /records/{id}``.

    Attributes:
        warnings: validation drops
        version: record version after the write
    """

    id: str
    warnings: list[str]
    version: str = Field(description=FIELD_DESCRIPTION_VERSION)


class RecordsDeleted(CamelModel):
    """Response of ``DELETE /records/{id}``.

    Attributes:
        deleted_ids: id of deleted record + ids of deleted orphans
        marked_ids: ids of records that lost their last parent link and were marked for review
    """

    deleted_ids: list[str]
    marked_ids: list[str]


class RecordToReview(CamelModel):
    """A marked record."""

    id: str
    review: str
    record: RecordNode
    version: str = Field(description=FIELD_DESCRIPTION_VERSION)


class Records(RootModel[list[RecordNode]]):
    """Response of ``GET /records``. Wraps list of validated nodes, sorted by id."""


class FileUpload(CamelModel):
    """Upload state of a file record."""

    id: str
    status: UploadStatus
    error_code: str | None
    size_bytes: int
    created_at: datetime
    updated_at: datetime


class RecordView(CamelModel):
    """A record with the extras asked for by ``include``."""

    record: RecordNode
    version: str = Field(description=FIELD_DESCRIPTION_VERSION)
    status: FileStatus | None = Field(
        default=None,
        description="Most urgent upload status of the record's files: uploading, processing, failed, ready.",
    )
    upload: FileUpload | None = Field(
        default=None, description=FIELD_DESCRIPTION_UPLOAD
    )
    children: list[RecordNode] | None = Field(
        default=None,
        description="Records whose parent links point to the record.",
    )


class RecordTree(CamelModel):
    """Response of ``GET /records/{id}/tree``. Record with every record below it."""

    record: RecordNode
    version: str = Field(description=FIELD_DESCRIPTION_VERSION)
    status: FileStatus | None = Field(
        default=None,
        description="Most urgent upload status of the record's files: uploading, processing, failed, ready.",
    )
    upload: FileUpload | None = Field(
        default=None, description=FIELD_DESCRIPTION_UPLOAD
    )
    children: list[RecordTree] = Field(
        description="Records whose parent links point to the record."
    )


class RecordAncestors(CamelModel):
    """Response of ``GET /records/{id}/ancestors``. Record with its parents up to the top."""

    record: RecordNode
    version: str = Field(description=FIELD_DESCRIPTION_VERSION)
    status: FileStatus | None = Field(
        default=None,
        description="Most urgent upload status of the record's files: uploading, processing, failed, ready.",
    )
    upload: FileUpload | None = Field(
        default=None, description=FIELD_DESCRIPTION_UPLOAD
    )
    parents: list[RecordAncestors] = Field(
        description="Records whose parent links point to the record."
    )


class UploadForm(CamelModel):
    """Presigned POST form: send ``fields`` and then the file as ``file`` to ``url``."""

    url: str
    fields: dict[str, str]


class OntologyProperty(CamelModel):
    """Property of an ontology class (``Ontology.describe``)."""

    range: str = Field(description="Local name of the range.")
    display_name: str
    comment: str
    enum: list[str] = Field(description="Allowed values, empty if any is allowed.")
    link: bool = Field(description="The value is the id of a record.")
    edge: EdgeType | None = Field(
        description="Kind of link: parent (the record's parent) or simple. Null if the property is no link."
    )
    delete_with_parent: bool = Field(
        description="Whether deleting the parent deletes the record too."
    )
    nested: bool = Field(description="Whether value is a nested node.")
    identity: bool = Field(description="Whether values name the record.")
    search: list[SearchMode]


class OntologyClass(CamelModel):
    """A class of the ontology (``Ontology.describe``)."""

    display_name: str
    comment: str
    record: bool = Field(description="Whether stored as records.")
    anchor: bool = Field(
        description="Whether class search results are grouped by this class."
    )
    file: bool = Field(description="Whether records carry an uploaded file.")
    guideline: bool = Field(description="Whether records are global guidelines.")
    extractable: bool = Field(
        description="Whether document import extracts records of this class."
    )
    properties: dict[str, OntologyProperty] = Field(
        description="In ontology file order."
    )


class OntologyDescription(CamelModel):
    """Response of ``GET /ontology``."""

    version: str = Field(description="Ontology content hash.")
    classes: dict[str, OntologyClass] = Field(description="Sorted by name.")
