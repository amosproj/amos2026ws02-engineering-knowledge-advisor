from __future__ import annotations

from dataclasses import dataclass

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.types import TypeEngine

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
    TableName,
    UpAxis,
    UploadColumn,
    UploadStatus,
    VectorColumn,
)
from services import VectorKind

ON_DELETE_CASCADE: str = "CASCADE"
ON_DELETE_RESTRICT: str = "RESTRICT"


@dataclass(frozen=True)
class Tables:
    """All relational database tables.

    Attributes:
        records: are sources of truth.
        uploads: holds metadata about uploads.
        ograg_*: tables that hold the hypergraph derived from the records.
    """

    metadata: MetaData

    records: Table
    record_links: Table
    uploads: Table

    # ograg_*
    vectors: Table
    hypernodes: Table
    facts: Table
    fact_nodes: Table


def define_tables(
    embedding_dimensions: int, metadata: MetaData | None = None
) -> Tables:
    """Creates and returns all tables.

    Args:
        embedding_dimensions: embedding model vector dimensionality.
        metadata: if ``None``, will create a new one.
    """
    metadata = metadata if metadata is not None else MetaData()
    records: Table = _define_records(metadata)
    hypernodes: Table = _define_hypernodes(metadata)
    facts: Table = _define_facts(metadata, records)
    return Tables(
        metadata,
        records=records,
        record_links=_define_links(metadata, records),
        uploads=_define_uploads(metadata, records),
        vectors=_define_vectors(metadata, embedding_dimensions),
        hypernodes=hypernodes,
        facts=facts,
        fact_nodes=_define_fact_nodes(metadata, hypernodes, facts),
    )


def _create_string_key(name: str = CommonColumn.ID) -> Column:
    return Column(name, String, primary_key=True)


def _create_counter_key(name: str = CommonColumn.ID) -> Column:
    return Column(name, BigInteger, Identity(), primary_key=True)


def _create_uuid_key(name: str = CommonColumn.ID) -> Column:
    return Column(name, Uuid, primary_key=True)


def _create_owner_reference(
    name: str,
    column_type: type[TypeEngine],
    owner: Column,
    *,
    primary_key: bool = False,
) -> Column:
    """Returns non-nullable column referencing ``owner``. Deleting ``owner`` row deletes this row (ON DELETE CASCADE).

    Args:
        name: name of column.
        column_type: type of column.
        owner: owner column (foreign key).
        primary_key: whether this column is a primary key.
    """
    return Column(
        name,
        column_type,
        ForeignKey(owner, ondelete=ON_DELETE_CASCADE),
        primary_key=primary_key,
        nullable=False,
    )


def _define_column_index(table: Table, column_name: str) -> None:
    """Defines a plain index ``ix_<table>_<column>`` on ``table``.``column_name``."""
    Index(f"ix_{table.name}_{column_name}", table.c[column_name])


def _create_timestamp(name: str) -> Column:
    """Returns a timestamp + timezone column set on row write."""
    return Column(
        name, DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def _define_records(metadata: MetaData) -> Table:
    """Returns table of records."""
    records = Table(
        TableName.RECORDS,
        metadata,
        _create_string_key(),
        Column(RecordColumn.CLS, String, nullable=False),
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
    _define_record_indices(records)
    return records


def _define_record_indices(records: Table) -> None:
    """Defines an index on classes, a partial index on records due for review, and GIN index on identity values."""
    _define_column_index(records, RecordColumn.CLS)
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


def _define_links(metadata: MetaData, records: Table) -> Table:
    """Returns a table of record links. Target cannot be deleted if linked (RESTRICT)."""
    links = Table(
        TableName.LINKS,
        metadata,
        _create_owner_reference(
            CommonColumn.RECORD_ID, String, records.c[CommonColumn.ID], primary_key=True
        ),
        Column(CommonColumn.POSITION, Integer, primary_key=True),
        Column(LinkColumn.PROPERTY_NAME, String, nullable=False),
        Column(
            LinkColumn.TARGET_ID,
            String,
            ForeignKey(records.c[CommonColumn.ID], ondelete=ON_DELETE_RESTRICT),
            nullable=False,
        ),
    )
    _define_column_index(links, LinkColumn.TARGET_ID)  # reverse lookups
    return links


def _define_uploads(metadata: MetaData, records: Table) -> Table:
    # Upload state of each CadFile record. The file name lives in the record, the files in S3.
    allowed_statuses: str = ", ".join(f"'{status}'" for status in UploadStatus)
    allowed_axes: str = ", ".join(f"'{axis}'" for axis in UpAxis)
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
        Column(
            UploadColumn.UP_AXIS,
            String,
            nullable=False,
            server_default=UpAxis.Z.value,
        ),
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
        CheckConstraint(
            f"{UploadColumn.UP_AXIS} IN ({allowed_axes})", name=UP_AXIS_CHECK
        ),
    )
    _define_processing_index(uploads)
    return uploads


def _define_processing_index(uploads: Table) -> None:
    """Defines a partial index on ``uploads`` in processing."""
    status: Column = uploads.c[UploadColumn.STATUS]
    # the worker takes the oldest file waiting in processing
    Index(
        PROCESSING_INDEX,
        uploads.c[UploadColumn.UPDATED_AT],
        postgresql_where=status == UploadStatus.PROCESSING,
    )


def _define_vectors(metadata: MetaData, dimensions: int) -> Table:
    vectors = Table(
        TableName.VECTORS,
        metadata,
        _create_string_key(VectorColumn.KIND),
        _create_uuid_key(),  # uuid5(embedding model name + text)
        Column(VectorColumn.MODEL, String, nullable=False),
        Column(VectorColumn.EMBEDDING, Vector(dimensions), nullable=False),
    )
    _define_vector_indices(vectors)
    return vectors


def _define_vector_indices(vectors: Table) -> None:
    """Defines a partial cosine distance HNSW index per vector kind."""
    for kind in VectorKind:
        Index(
            f"{TableName.VECTORS}_{kind.value}_hnsw",
            vectors.c[VectorColumn.EMBEDDING],
            postgresql_using="hnsw",
            postgresql_ops={VectorColumn.EMBEDDING.value: "vector_cosine_ops"},
            postgresql_where=vectors.c[VectorColumn.KIND] == kind.value,
        )


def _define_hypernodes(metadata: MetaData) -> Table:
    hypernodes = Table(
        TableName.HYPERNODES,
        metadata,
        _create_uuid_key(),  # uuid5(key + separator + value)
        Column(HypernodeColumn.KEY, Text, nullable=False),
        Column(CommonColumn.VALUE, Text, nullable=False),
        Column(HypernodeColumn.KEY_VID, Uuid, nullable=False),
        Column(HypernodeColumn.VALUE_VID, Uuid),
        Column(HypernodeColumn.LEXICAL, Boolean, nullable=False),
    )
    _define_column_index(hypernodes, HypernodeColumn.KEY_VID)
    _define_column_index(hypernodes, HypernodeColumn.VALUE_VID)
    _define_spelling_index(hypernodes)
    return hypernodes


def _define_spelling_index(hypernodes: Table) -> None:
    """Defines a partial GIN trigram index on lexical values of ``hypernodes`` rows."""
    Index(
        f"{TableName.HYPERNODES}_value_trgm",
        hypernodes.c[CommonColumn.VALUE],
        postgresql_using="gin",
        postgresql_ops={CommonColumn.VALUE.value: "gin_trgm_ops"},
        postgresql_where=hypernodes.c[HypernodeColumn.LEXICAL],
    )


def _define_facts(metadata: MetaData, records: Table) -> Table:
    facts = Table(
        TableName.FACTS,
        metadata,
        _create_counter_key(),
        _create_owner_reference(
            CommonColumn.RECORD_ID, String, records.c[CommonColumn.ID]
        ),
        Column(CommonColumn.ANCHOR_ID, String),
        Column(CommonColumn.LANE, String, nullable=False),
        Column(FactColumn.SORT_KEY, String, nullable=False),
        Column(FactColumn.TEXT, Text, nullable=False),
    )
    _define_column_index(facts, CommonColumn.RECORD_ID)
    return facts


def _define_fact_nodes(metadata: MetaData, hypernodes: Table, facts: Table) -> Table:
    fact_nodes = Table(
        TableName.FACT_NODES,
        metadata,
        Column(CommonColumn.LANE, String, primary_key=True),
        Column(
            CommonColumn.NODE_ID,
            Uuid,
            ForeignKey(hypernodes.c[CommonColumn.ID]),
            primary_key=True,
        ),
        _create_owner_reference(
            FactNodeColumn.FACT_ID,
            BigInteger,
            facts.c[CommonColumn.ID],
            primary_key=True,
        ),
        Column(CommonColumn.POSITION, Integer, nullable=False),
    )
    _define_fact_node_indices(fact_nodes)
    return fact_nodes


def _define_fact_node_indices(fact_nodes: Table) -> None:
    """Defines a unique index on the pair order per fact, and index on hypernode memberships for reverse lookup."""
    Index(
        f"{TableName.FACT_NODES}_fact_position",
        fact_nodes.c[FactNodeColumn.FACT_ID],
        fact_nodes.c[CommonColumn.POSITION],
        unique=True,
    )
    Index(f"{TableName.FACT_NODES}_node", fact_nodes.c[CommonColumn.NODE_ID])
