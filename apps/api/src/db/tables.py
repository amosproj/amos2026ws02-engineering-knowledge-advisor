from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.types import TypeEngine

from db.names import (
    PROCESSING_INDEX,
    STATUS_CHECK,
    CommonColumn,
    LinkColumn,
    RecordColumn,
    TableName,
    UploadColumn,
    UploadStatus,
)

ON_DELETE_CASCADE: str = "CASCADE"
ON_DELETE_RESTRICT: str = "RESTRICT"


@dataclass(frozen=True)
class Tables:
    """All relational database tables."""

    metadata: MetaData

    records: Table
    record_links: Table
    uploads: Table


def define_tables(metadata: MetaData | None = None) -> Tables:
    """Creates and returns all tables.

    Args:
        metadata: if ``None``, will create a new one.
    """
    metadata = metadata if metadata is not None else MetaData()
    records: Table = _define_records(metadata)
    return Tables(
        metadata,
        records=records,
        record_links=_define_links(metadata, records),
        uploads=_define_uploads(metadata, records),
    )


def _create_string_key(name: str = CommonColumn.ID) -> Column:
    return Column(name, String, primary_key=True)


def _create_owner_reference(
    name: str,
    column_type: type[TypeEngine],
    owner: Column,
    *,
    primary_key: bool = False,
    index: bool = False,
) -> Column:
    """Returns non-nullable column referencing ``owner``. Deleting ``owner`` row deletes this row (ON DELETE CASCADE).

    Args:
        name: name of column.
        column_type: type of column.
        owner: owner column (foreign key).
        primary_key: whether this column is a primary key.
        index: whether this column should auto-init index (CREATE INDEX).
    """
    return Column(
        name,
        column_type,
        ForeignKey(owner, ondelete=ON_DELETE_CASCADE),
        primary_key=primary_key,
        nullable=False,
        index=index,
    )


def _create_timestamp(name: str) -> Column:
    """Returns a timestamp + timezone column set on row write."""
    return Column(
        name, DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def _define_records(metadata: MetaData) -> Table:
    """Returns table of records. The partial index is for records due for review."""
    records = Table(
        TableName.RECORDS,
        metadata,
        _create_string_key(),
        Column(RecordColumn.CLS, String, nullable=False, index=True),
        Column(RecordColumn.GRAPH, JSONB, nullable=False),
        Column(RecordColumn.INPUT, JSONB, nullable=False),
        Column(RecordColumn.ONTOLOGY_VERSION, String, nullable=False),
        Column(RecordColumn.REVIEW, Text, nullable=False, server_default=""),
        _create_timestamp(RecordColumn.UPDATED_AT),
        Column(
            RecordColumn.IDENTITY_VALUES,
            ARRAY(Text),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )
    Index(
        f"{TableName.RECORDS}_review",
        records.c[CommonColumn.ID],
        postgresql_where=records.c[RecordColumn.REVIEW] != "",
    )
    Index(
        f"{TableName.RECORDS}_identity_values",
        records.c[RecordColumn.IDENTITY_VALUES],
        postgresql_using="gin",
    )
    return records


def _define_links(metadata: MetaData, records: Table) -> Table:
    """Returns a table of record links. Target cannot be deleted if linked (RESTRICT)."""
    return Table(
        TableName.LINKS,
        metadata,
        _create_owner_reference(
            CommonColumn.RECORD_ID, String, records.c[CommonColumn.ID], primary_key=True
        ),
        Column(LinkColumn.POSITION, Integer, primary_key=True),
        Column(LinkColumn.PROPERTY_NAME, String, nullable=False),
        Column(
            LinkColumn.TARGET_ID,
            String,
            ForeignKey(records.c[CommonColumn.ID], ondelete=ON_DELETE_RESTRICT),
            nullable=False,
            index=True,
        ),
    )


def _define_uploads(metadata: MetaData, records: Table) -> Table:
    # Upload state of each CadFile record. The file name lives in the record, the files in S3.
    allowed_statuses: str = ", ".join(f"'{status}'" for status in UploadStatus)
    uploads = Table(
        TableName.UPLOADS,
        metadata,
        _create_owner_reference(
            UploadColumn.FILE_ID,
            String,
            records.c[CommonColumn.ID],
            primary_key=True,
        ),
        Column(
            UploadColumn.STATUS,
            String,
            nullable=False,
            server_default=UploadStatus.UPLOADING.value,
        ),
        Column(UploadColumn.ERROR_CODE, String),
        Column(UploadColumn.SOURCE_KEY, String, nullable=False, unique=True),
        Column(UploadColumn.PREVIEW_KEY, String),
        Column(UploadColumn.MODEL_KEY, String),
        Column(UploadColumn.SIZE_BYTES, BigInteger, nullable=False),
        Column(UploadColumn.SHA256, CHAR(64)),
        _create_timestamp(UploadColumn.CREATED_AT),
        Column(
            UploadColumn.UPDATED_AT,
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
        CheckConstraint(
            f"{UploadColumn.STATUS} IN ({allowed_statuses})", name=STATUS_CHECK
        ),
    )
    status: Column = uploads.c[UploadColumn.STATUS]
    # the worker takes the oldest file waiting in processing
    Index(
        PROCESSING_INDEX,
        uploads.c[UploadColumn.UPDATED_AT],
        postgresql_where=status == UploadStatus.PROCESSING,
    )
    return uploads
