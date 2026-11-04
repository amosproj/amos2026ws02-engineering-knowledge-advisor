from enum import StrEnum

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    func,
    text,
)

from db.model_base import ModelBase, get_ograg_tables
from services.postgres.names import CommonColumn, TableName


class CadUploadColumn(StrEnum):
    CAD_FILE_ID = "cad_file_id"
    STATUS = "status"
    ERROR_CODE = "error_code"
    SOURCE_KEY = "source_key"
    PREVIEW_KEY = "preview_key"
    MODEL_KEY = "model_key"
    SIZE_BYTES = "size_bytes"
    SHA256 = "sha256"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class CadUploadStatus(StrEnum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


SHA256_READY_INDEX: str = "uq_cad_uploads_sha256_ready"

get_ograg_tables()  # the foreign key needs ograg_records on the same metadata

# Upload state of each CadFile record. The file name lives in the record, the files in S3.
cad_uploads: Table = Table(
    "cad_uploads",
    ModelBase.metadata,
    Column(
        CadUploadColumn.CAD_FILE_ID,
        String,
        ForeignKey(f"{TableName.RECORDS}.{CommonColumn.ID}", ondelete="CASCADE"),
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
    Column(
        CadUploadColumn.CREATED_AT,
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        CadUploadColumn.UPDATED_AT,
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
    CheckConstraint(
        "status IN ('uploading', 'processing', 'ready', 'failed')",
        name="ck_cad_uploads_status",
    ),
    # the same content may be ready only once
    Index(
        SHA256_READY_INDEX,
        CadUploadColumn.SHA256,
        unique=True,
        postgresql_where=text("status = 'ready'"),
    ),
    # the worker takes the oldest file waiting in processing
    Index(
        "ix_cad_uploads_processing",
        CadUploadColumn.UPDATED_AT,
        postgresql_where=text("status = 'processing'"),
    ),
)
