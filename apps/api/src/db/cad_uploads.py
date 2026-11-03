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
        "cad_file_id",
        String,
        ForeignKey("ograg_records.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "status",
        String,
        nullable=False,
        server_default=CadUploadStatus.UPLOADING.value,
    ),
    Column("error_code", String),
    Column("source_key", String, nullable=False, unique=True),
    Column("preview_key", String),
    Column("model_key", String),
    Column("size_bytes", BigInteger, nullable=False),
    Column("sha256", CHAR(64)),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    Column(
        "updated_at",
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
        "sha256",
        unique=True,
        postgresql_where=text("status = 'ready'"),
    ),
    # the worker takes the oldest file waiting in processing
    Index(
        "ix_cad_uploads_processing",
        "updated_at",
        postgresql_where=text("status = 'processing'"),
    ),
)
