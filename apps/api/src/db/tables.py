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
    CadUploadColumn,
    CadUploadStatus,
    CommonColumn,
    LinkColumn,
    RecordColumn,
    TableName,
)

ON_DELETE_CASCADE: str = "CASCADE"
ON_DELETE_RESTRICT: str = "RESTRICT"


@dataclass(frozen=True)
class Tables:
    """All knowledge tables used for OG-RAG."""

    metadata: MetaData

    records: Table
    links: Table
    cad_uploads: Table


def define_tables(metadata: MetaData | None = None) -> Tables:
    """Creates and returns all OG-RAG tables.

    Args:
        metadata: if ``None``, will create a new one.
    """
    metadata = metadata if metadata is not None else MetaData()
    records: Table = _define_records(metadata)
    return Tables(
        metadata,
        records=records,
        links=_define_links(metadata, records),
        cad_uploads=_define_cad_uploads(metadata, records),
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


def _define_cad_uploads(metadata: MetaData, records: Table) -> Table:
    # Upload state of each CadFile record. The file name lives in the record, the files in S3.
    allowed_statuses: str = ", ".join(f"'{status}'" for status in CadUploadStatus)
    cad_uploads = Table(
        TableName.CAD_UPLOADS,
        metadata,
        _create_owner_reference(
            CadUploadColumn.CAD_FILE_ID,
            String,
            records.c[CommonColumn.ID],
            primary_key=True,
        ),
        Column(
            CadUploadColumn.STATUS,
            String,
            nullable=False,
            server_default=CadUploadStatus.UPLOADING.value,
        ),
        Column(CadUploadColumn.ERROR_CODE, String),
        Column(CadUploadColumn.SOURCE_KEY, String, nullable=False, unique=True),
        Column(CadUploadColumn.PREVIEW_KEY, String),
        Column(CadUploadColumn.MODEL_KEY, String),
        Column(CadUploadColumn.SIZE_BYTES, BigInteger, nullable=False),
        Column(CadUploadColumn.SHA256, CHAR(64)),
        _create_timestamp(CadUploadColumn.CREATED_AT),
        Column(
            CadUploadColumn.UPDATED_AT,
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
        CheckConstraint(
            f"{CadUploadColumn.STATUS} IN ({allowed_statuses})", name=STATUS_CHECK
        ),
    )
    status: Column = cad_uploads.c[CadUploadColumn.STATUS]
    # the worker takes the oldest file waiting in processing
    Index(
        PROCESSING_INDEX,
        cad_uploads.c[CadUploadColumn.UPDATED_AT],
        postgresql_where=status == CadUploadStatus.PROCESSING,
    )
    return cad_uploads
