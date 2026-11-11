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
FIELD_DESCRIPTION_RECORD: str = "Validated record. Links hold target ids."
FIELD_DESCRIPTION_RECORD_ID: str = "Record id."
FIELD_DESCRIPTION_DISPLAY_NAME: str = "Name to show."
FIELD_DESCRIPTION_COMMENT: str = "What it means."


class RecordWritten(CamelModel):
    """Response of ``POST /records``, ``PUT /records/{id}`` and ``PATCH /records/{id}``.

    Attributes:
        warnings: validation drops
        version: record version after the write
    """

    id: str = Field(description=FIELD_DESCRIPTION_RECORD_ID)
    warnings: list[str] = Field(description="Validation drops: what was left out.")
    version: str = Field(description=FIELD_DESCRIPTION_VERSION)


class RecordsDeleted(CamelModel):
    """Response of ``DELETE /records/{id}``.

    Attributes:
        deleted_ids: id of deleted record + ids of deleted orphans
        marked_ids: ids of records that lost their last parent link and were marked for review
    """

    deleted_ids: list[str] = Field(
        description="The record and every record deleted with it."
    )
    marked_ids: list[str] = Field(
        description="Records that lost their last parent link, marked for review."
    )


class RecordToReview(CamelModel):
    """A marked record."""

    id: str = Field(description=FIELD_DESCRIPTION_RECORD_ID)
    review: str = Field(description="Why the record needs a review.")
    record: RecordNode = Field(description=FIELD_DESCRIPTION_RECORD)
    version: str = Field(description=FIELD_DESCRIPTION_VERSION)


class Records(RootModel[list[RecordNode]]):
    """Response of ``GET /records``. Wraps list of validated nodes, sorted by id."""


class FileUpload(CamelModel):
    """Upload state of a file record."""

    id: str = Field(description="File record id.")
    status: UploadStatus = Field(description="Where the file is in its life cycle.")
    error_code: str | None = Field(description="Why the file failed, else null.")
    size_bytes: int = Field(description="Announced size, checked on complete.")
    created_at: datetime = Field(description="When the upload form was requested.")
    updated_at: datetime = Field(description="Last status change.")


class RecordView(CamelModel):
    """A record with the extras asked for by ``include``."""

    record: RecordNode = Field(description=FIELD_DESCRIPTION_RECORD)
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

    record: RecordNode = Field(description=FIELD_DESCRIPTION_RECORD)
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

    record: RecordNode = Field(description=FIELD_DESCRIPTION_RECORD)
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

    url: str = Field(description="Where to post the form.")
    fields: dict[str, str] = Field(description="Form fields, sent before the file.")


class OntologyProperty(CamelModel):
    """Property of an ontology class (``Ontology.describe``)."""

    range: str = Field(description="Local name of the range.")
    display_name: str = Field(description=FIELD_DESCRIPTION_DISPLAY_NAME)
    comment: str = Field(description=FIELD_DESCRIPTION_COMMENT)
    enum: list[str] = Field(description="Allowed values, empty if any is allowed.")
    link: bool = Field(description="The value is the id of a record.")
    edge: EdgeType | None = Field(
        description="Kind of link: parent (the record's parent) or simple. Null if the property is no link."
    )
    delete_with_parent: bool = Field(
        description="Whether deleting the parent deletes the record too."
    )
    max_per_parent: int | None = Field(
        description="Most records of the class one parent may have through this link, null for any."
    )
    nested: bool = Field(description="Whether value is a nested node.")
    identity: bool = Field(description="Whether values name the record.")
    search: list[SearchMode] = Field(description="How values are searched.")


class OntologyClass(CamelModel):
    """A class of the ontology (``Ontology.describe``)."""

    display_name: str = Field(description=FIELD_DESCRIPTION_DISPLAY_NAME)
    comment: str = Field(description=FIELD_DESCRIPTION_COMMENT)
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
