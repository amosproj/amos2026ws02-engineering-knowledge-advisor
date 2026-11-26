from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Table,
    Text,
    Uuid,
    cast,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, MappedColumn, column_property, mapped_column
from sqlalchemy.types import TypeEngine

from config.settings import get_schema_settings
from db.model_base import ModelBase
from db.names import (
    PROCESSING_INDEX,
    STATUS_CHECK,
    UP_AXIS_CHECK,
    CommonColumn,
    FactColumn,
    FactNodeColumn,
    HypernodeColumn,
    LinkColumn,
    RecordColumn,
    SystemColumn,
    TableName,
    UpAxis,
    UploadColumn,
    UploadStatus,
    VectorColumn,
)
from services import JsonObject, VectorKind

ON_DELETE_CASCADE: str = "CASCADE"
ON_DELETE_RESTRICT: str = "RESTRICT"
RECORD_KEY: str = f"{TableName.RECORDS}.{CommonColumn.ID}"
HYPERNODE_KEY: str = f"{TableName.HYPERNODES}.{CommonColumn.ID}"
FACT_KEY: str = f"{TableName.FACTS}.{CommonColumn.ID}"
ALLOWED_STATUSES: str = ", ".join(f"'{status}'" for status in UploadStatus)
ALLOWED_AXES: str = ", ".join(f"'{axis}'" for axis in UpAxis)


def _create_string_key(name: str = CommonColumn.ID) -> MappedColumn[str]:
    return mapped_column(name, String, primary_key=True)


def _create_counter_key(name: str = CommonColumn.ID) -> MappedColumn[int]:
    return mapped_column(name, BigInteger, Identity(), primary_key=True)


def _create_uuid_key(name: str = CommonColumn.ID) -> MappedColumn[UUID]:
    return mapped_column(name, Uuid, primary_key=True)


def _create_owner_reference[T](
    name: str,
    column_type: type[TypeEngine[T]],
    owner: str,
    *,
    primary_key: bool = False,
) -> MappedColumn[T]:
    """Returns non-nullable column referencing ``owner``. Deleting ``owner`` row deletes this row (ON DELETE CASCADE).

    Args:
        name: name of column.
        column_type: type of column.
        owner: owner column (foreign key).
        primary_key: whether this column is a primary key.
    """
    return mapped_column(
        name,
        column_type,
        ForeignKey(owner, ondelete=ON_DELETE_CASCADE),
        primary_key=primary_key,
        nullable=False,
    )


def _define_column_index(table: Table, column_name: str) -> None:
    """Defines a plain index ``ix_<table>_<column>`` on ``table``.``column_name``."""
    Index(f"ix_{table.name}_{column_name}", table.c[column_name])


def _create_timestamp(name: str) -> MappedColumn[datetime]:
    """Returns a timestamp + timezone column set on row write."""
    return mapped_column(
        name, DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RecordModel(ModelBase):
    """Table of records."""

    __tablename__ = TableName.RECORDS

    id: Mapped[str] = _create_string_key()
    cls: Mapped[str] = mapped_column(RecordColumn.CLS, String, nullable=False)
    graph: Mapped[JsonObject] = mapped_column(RecordColumn.GRAPH, JSONB, nullable=False)
    input: Mapped[JsonObject] = mapped_column(RecordColumn.INPUT, JSONB, nullable=False)
    ontology_version: Mapped[str] = mapped_column(
        RecordColumn.ONTOLOGY_VERSION, String, nullable=False
    )
    review: Mapped[str] = mapped_column(
        RecordColumn.REVIEW, Text, nullable=False, server_default=""
    )
    updated_at: Mapped[datetime] = _create_timestamp(RecordColumn.UPDATED_AT)
    identity_values: Mapped[list[str]] = mapped_column(
        RecordColumn.IDENTITY_VALUES,
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'"),
    )
    # xmin as text, Postgres sets it every row write
    version: Mapped[str] = column_property(
        cast(literal_column(f"{TableName.RECORDS}.{SystemColumn.XMIN}"), Text)
    )


def _define_record_indices() -> None:
    """Defines an index on classes, a partial index on records due for review, and GIN index on identity values."""
    _define_column_index(RecordModel.get_table(), RecordColumn.CLS)
    Index(
        f"{TableName.RECORDS}_review",
        RecordModel.id,
        postgresql_where=RecordModel.review != "",
    )
    Index(
        f"{TableName.RECORDS}_identity_values",
        RecordModel.identity_values,
        postgresql_using="gin",
    )


_define_record_indices()


class LinkModel(ModelBase):
    """A table of record links. Target cannot be deleted if linked (RESTRICT)."""

    __tablename__ = TableName.LINKS

    record_id: Mapped[str] = _create_owner_reference(
        CommonColumn.RECORD_ID, String, RECORD_KEY, primary_key=True
    )
    position: Mapped[int] = mapped_column(
        CommonColumn.POSITION, Integer, primary_key=True
    )
    property_name: Mapped[str] = mapped_column(
        LinkColumn.PROPERTY_NAME, String, nullable=False
    )
    target_id: Mapped[str] = mapped_column(
        LinkColumn.TARGET_ID,
        String,
        ForeignKey(RECORD_KEY, ondelete=ON_DELETE_RESTRICT),
        nullable=False,
    )


_define_column_index(LinkModel.get_table(), LinkColumn.TARGET_ID)  # reverse lookups


class UploadModel(ModelBase):
    # Upload state of each CadFile record. The file name lives in the record, the files in S3.

    __tablename__ = TableName.UPLOADS
    __table_args__ = (
        CheckConstraint(
            f"{UploadColumn.STATUS} IN ({ALLOWED_STATUSES})", name=STATUS_CHECK
        ),
        CheckConstraint(
            f"{UploadColumn.UP_AXIS} IN ({ALLOWED_AXES})", name=UP_AXIS_CHECK
        ),
    )

    file_id: Mapped[str] = _create_owner_reference(
        UploadColumn.FILE_ID, String, RECORD_KEY, primary_key=True
    )
    status: Mapped[str] = mapped_column(
        UploadColumn.STATUS,
        String,
        nullable=False,
        server_default=UploadStatus.UPLOADING.value,
    )
    error_code: Mapped[str | None] = mapped_column(UploadColumn.ERROR_CODE, String)
    source_key: Mapped[str] = mapped_column(
        UploadColumn.SOURCE_KEY, String, nullable=False, unique=True
    )
    preview_key: Mapped[str | None] = mapped_column(UploadColumn.PREVIEW_KEY, String)
    model_key: Mapped[str | None] = mapped_column(UploadColumn.MODEL_KEY, String)
    size_bytes: Mapped[int] = mapped_column(
        UploadColumn.SIZE_BYTES, BigInteger, nullable=False
    )
    sha256: Mapped[str | None] = mapped_column(UploadColumn.SHA256, CHAR(64))
    up_axis: Mapped[str] = mapped_column(
        UploadColumn.UP_AXIS, String, nullable=False, server_default=UpAxis.Z.value
    )
    created_at: Mapped[datetime] = _create_timestamp(UploadColumn.CREATED_AT)
    updated_at: Mapped[datetime] = mapped_column(
        UploadColumn.UPDATED_AT,
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


def _define_processing_index() -> None:
    """Defines a partial index on ``uploads`` in processing."""
    # the worker takes the oldest file waiting in processing
    Index(
        PROCESSING_INDEX,
        UploadModel.updated_at,
        postgresql_where=UploadModel.status == UploadStatus.PROCESSING,
    )


_define_processing_index()


class VectorModel(ModelBase):
    __tablename__ = TableName.VECTORS

    kind: Mapped[str] = _create_string_key(VectorColumn.KIND)
    id: Mapped[UUID] = _create_uuid_key()  # uuid5(embedding model name + text)
    model: Mapped[str] = mapped_column(VectorColumn.MODEL, String, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        VectorColumn.EMBEDDING,
        Vector(get_schema_settings().embedding_dimensions),
        nullable=False,
    )


def _define_vector_indices() -> None:
    """Defines a partial cosine distance HNSW index per vector kind."""
    for kind in VectorKind:
        Index(
            f"{TableName.VECTORS}_{kind.value}_hnsw",
            VectorModel.embedding,
            postgresql_using="hnsw",
            postgresql_ops={VectorColumn.EMBEDDING.value: "vector_cosine_ops"},
            postgresql_where=VectorModel.kind == kind.value,
        )


_define_vector_indices()


class HypernodeModel(ModelBase):
    __tablename__ = TableName.HYPERNODES

    id: Mapped[UUID] = _create_uuid_key()  # uuid5(key + separator + value)
    key: Mapped[str] = mapped_column(HypernodeColumn.KEY, Text, nullable=False)
    value: Mapped[str] = mapped_column(CommonColumn.VALUE, Text, nullable=False)
    key_vid: Mapped[UUID] = mapped_column(HypernodeColumn.KEY_VID, Uuid, nullable=False)
    value_vid: Mapped[UUID | None] = mapped_column(HypernodeColumn.VALUE_VID, Uuid)
    lexical: Mapped[bool] = mapped_column(
        HypernodeColumn.LEXICAL, Boolean, nullable=False
    )


def _define_spelling_index() -> None:
    """Defines a partial GIN trigram index on lexical values of ``hypernodes`` rows."""
    Index(
        f"{TableName.HYPERNODES}_value_trgm",
        HypernodeModel.value,
        postgresql_using="gin",
        postgresql_ops={CommonColumn.VALUE.value: "gin_trgm_ops"},
        postgresql_where=HypernodeModel.lexical,
    )


_define_column_index(HypernodeModel.get_table(), HypernodeColumn.KEY_VID)
_define_column_index(HypernodeModel.get_table(), HypernodeColumn.VALUE_VID)
_define_spelling_index()


class FactModel(ModelBase):
    __tablename__ = TableName.FACTS

    id: Mapped[int] = _create_counter_key()
    record_id: Mapped[str] = _create_owner_reference(
        CommonColumn.RECORD_ID, String, RECORD_KEY
    )
    anchor_id: Mapped[str | None] = mapped_column(CommonColumn.ANCHOR_ID, String)
    lane: Mapped[str] = mapped_column(CommonColumn.LANE, String, nullable=False)
    sort_key: Mapped[str] = mapped_column(FactColumn.SORT_KEY, String, nullable=False)
    text: Mapped[str] = mapped_column(FactColumn.TEXT, Text, nullable=False)


_define_column_index(FactModel.get_table(), CommonColumn.RECORD_ID)


class FactNodeModel(ModelBase):
    __tablename__ = TableName.FACT_NODES

    lane: Mapped[str] = mapped_column(CommonColumn.LANE, String, primary_key=True)
    node_id: Mapped[UUID] = mapped_column(
        CommonColumn.NODE_ID, Uuid, ForeignKey(HYPERNODE_KEY), primary_key=True
    )
    fact_id: Mapped[int] = _create_owner_reference(
        FactNodeColumn.FACT_ID, BigInteger, FACT_KEY, primary_key=True
    )
    position: Mapped[int] = mapped_column(
        CommonColumn.POSITION, Integer, nullable=False
    )


def _define_fact_node_indices() -> None:
    """Defines a unique index on the pair order per fact, and index on hypernode memberships for reverse lookup."""
    Index(
        f"{TableName.FACT_NODES}_fact_position",
        FactNodeModel.fact_id,
        FactNodeModel.position,
        unique=True,
    )
    Index(f"{TableName.FACT_NODES}_node", FactNodeModel.node_id)


_define_fact_node_indices()
