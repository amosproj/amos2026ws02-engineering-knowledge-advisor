from __future__ import annotations

from dataclasses import dataclass

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Identity,
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

from services import VectorKind
from services.postgres.names import (
    CommonColumn,
    DocumentColumn,
    DocumentRecordColumn,
    FactColumn,
    FactNodeColumn,
    HypernodeColumn,
    LinkColumn,
    NumberColumn,
    RecordColumn,
    TableName,
    VectorColumn,
)

ON_DELETE_CASCADE: str = "CASCADE"
ON_DELETE_RESTRICT: str = "RESTRICT"


@dataclass(frozen=True)
class Tables:
    """All knowledge tables used for OG-RAG."""

    metadata: MetaData

    records: Table
    vectors: Table
    documents: Table
    document_records: Table
    links: Table
    hypernodes: Table
    facts: Table
    fact_nodes: Table
    numbers: Table


def define_tables(dim: int, metadata: MetaData | None = None) -> Tables:
    """Creates and returns all OG-RAG tables.

    Args:
        metadata: if ``None``, will create a new one.
        dim: embedding size.
    """
    metadata = metadata if metadata is not None else MetaData()
    records: Table = _define_records(metadata)
    documents: Table = _define_documents(metadata)
    hypernodes: Table = _define_hypernodes(metadata)
    facts: Table = _define_facts(metadata, records)
    return Tables(
        metadata,
        records=records,
        vectors=_define_vectors(metadata, dim),
        documents=documents,
        document_records=_define_document_records(metadata, documents, records),
        links=_define_links(metadata, records),
        hypernodes=hypernodes,
        facts=facts,
        fact_nodes=_define_fact_nodes(metadata, hypernodes, facts),
        numbers=_define_numbers(metadata, records),
    )


def _create_string_key(name: str = CommonColumn.ID) -> Column:
    return Column(name, String, primary_key=True)


def _create_identity_key(name: str = CommonColumn.ID) -> Column:
    return Column(name, BigInteger, Identity(), primary_key=True)


def _create_owner_reference(
    name: str,
    column_type: type[TypeEngine],
    owner: Column,
    *,
    primary_key: bool = False,
    index: bool = False,
) -> Column:
    """Returns non-nullable column referencing ``owner``. Deleting ``owner`` row deletes this row due to ON DELETE CASCADE.

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


def _define_vectors(metadata: MetaData, dim: int) -> Table:
    """Returns a table of embeddings ``dim`` dimensions per vector kind."""
    vectors = Table(
        TableName.VECTORS,
        metadata,
        _create_string_key(VectorColumn.KIND),
        _create_string_key(),  # uuid5 of embedder name + text
        Column(CommonColumn.TEXT, Text, nullable=False),
        Column(VectorColumn.EMBEDDING, Vector(dim), nullable=False),
    )
    _define_vector_indexes(vectors)
    return vectors


def _define_vector_indexes(vectors: Table) -> None:
    """Runs one partial HNSW index per kind."""
    for kind in VectorKind:
        Index(
            f"{TableName.VECTORS}_{kind.value}_hnsw",
            vectors.c[VectorColumn.EMBEDDING],
            postgresql_using="hnsw",
            postgresql_ops={VectorColumn.EMBEDDING: "vector_cosine_ops"},
            postgresql_where=vectors.c[VectorColumn.KIND] == kind.value,
        )


def _define_documents(metadata: MetaData) -> Table:
    """Returns table of source documents."""
    return Table(
        TableName.DOCUMENTS,
        metadata,
        _create_string_key(),
        Column(DocumentColumn.URI, String, nullable=False),
        Column(DocumentColumn.MEDIA_TYPE, String, nullable=False),
        Column(DocumentColumn.SHA256, String, nullable=False, unique=True),
        Column(DocumentColumn.NAME, String, nullable=False),
        Column(DocumentColumn.STATUS, String, nullable=False),
        Column(DocumentColumn.ERROR, Text, nullable=False),
        Column(DocumentColumn.NOTES, JSONB, nullable=False),
        Column(DocumentColumn.EXTRACTOR, String, nullable=False),
        Column(DocumentColumn.PROPERTIES, JSONB, nullable=False),
        Column(DocumentColumn.META, JSONB, nullable=False),
        Column(DocumentColumn.AUTHOR, String, nullable=False, server_default=""),
        _create_timestamp(DocumentColumn.CREATED_AT),
    )


def _define_document_records(
    metadata: MetaData, documents: Table, records: Table
) -> Table:
    """Returns table of links between rows of ``documents`` and ``records``."""
    return Table(
        TableName.DOCUMENT_RECORDS,
        metadata,
        _create_owner_reference(
            DocumentRecordColumn.DOCUMENT_ID,
            String,
            documents.c[CommonColumn.ID],
            primary_key=True,
        ),
        _create_owner_reference(
            CommonColumn.RECORD_ID,
            String,
            records.c[CommonColumn.ID],
            primary_key=True,
            index=True,
        ),
    )


def _define_hypernodes(metadata: MetaData) -> Table:
    """Returns table of hypernodes (``key: value`` pairs). A hypernode is shared by all facts (hyperedges) containing it."""
    hypernodes = Table(
        TableName.HYPERNODES,
        metadata,
        _create_identity_key(),
        Column(
            HypernodeColumn.KV_HASH, String, nullable=False, unique=True
        ),  # sha256 of key and value
        Column(HypernodeColumn.KEY, Text, nullable=False),
        Column(CommonColumn.VALUE, Text, nullable=False),
        Column(HypernodeColumn.KEY_VID, String, nullable=False),
        Column(HypernodeColumn.VALUE_VID, String, index=True),
        Column(HypernodeColumn.LEXICAL, Boolean, nullable=False),
    )
    _define_spelling_index(hypernodes)
    return hypernodes


def _define_spelling_index(hypernodes: Table) -> None:
    """Defines a partial GIN trigram index (``pg_trgm``) on values of lexical rows of ``hypernodes``."""
    Index(
        f"{TableName.HYPERNODES}_value_trgm",
        hypernodes.c[CommonColumn.VALUE],
        postgresql_using="gin",
        postgresql_ops={CommonColumn.VALUE: "gin_trgm_ops"},
        postgresql_where=hypernodes.c[HypernodeColumn.LEXICAL],
    )


def _define_facts(metadata: MetaData, records: Table) -> Table:
    """Returns table of facts (hyperedges) built from rows of ``records``."""
    return Table(
        TableName.FACTS,
        metadata,
        _create_identity_key(),
        _create_owner_reference(
            CommonColumn.RECORD_ID, String, records.c[CommonColumn.ID], index=True
        ),
        Column(CommonColumn.ANCHOR_ID, String),
        Column(CommonColumn.LANE, String, nullable=False),
        Column(FactColumn.PAIR_COUNT, Integer, nullable=False),
        Column(FactColumn.SORT_KEY, String, nullable=False),
        Column(CommonColumn.TEXT, Text, nullable=False),
        Column(FactColumn.PAIRS, JSONB, nullable=False),  # [[key, value], ...]
    )


def _define_fact_nodes(metadata: MetaData, hypernodes: Table, facts: Table) -> Table:
    """Returns table of memberships i.e. many-to-many relationships between ``hypernodes`` and ``facts`` (hyperedges)."""
    fact_nodes = Table(
        TableName.FACT_NODES,
        metadata,
        Column(CommonColumn.LANE, String, primary_key=True),
        Column(
            CommonColumn.NODE_ID,
            BigInteger,
            ForeignKey(hypernodes.c[CommonColumn.ID]),
            primary_key=True,
        ),
        _create_owner_reference(
            FactNodeColumn.FACT_ID,
            BigInteger,
            facts.c[CommonColumn.ID],
            primary_key=True,
        ),
    )
    Index(
        f"{TableName.FACT_NODES}_fact",
        fact_nodes.c[FactNodeColumn.FACT_ID],
        fact_nodes.c[CommonColumn.NODE_ID],
    )
    return fact_nodes


def _define_numbers(metadata: MetaData, records: Table) -> Table:
    """Returns table of filter property values per anchor record id."""
    numbers = Table(
        TableName.NUMBERS,
        metadata,
        _create_owner_reference(
            CommonColumn.RECORD_ID, String, records.c[CommonColumn.ID], index=True
        ),
        Column(CommonColumn.ANCHOR_ID, String, nullable=False),
        Column(NumberColumn.PATH, String, nullable=False),
        Column(CommonColumn.VALUE, Float, nullable=False),
    )
    Index(
        f"{TableName.NUMBERS}_path_value",
        numbers.c[NumberColumn.PATH],
        numbers.c[CommonColumn.VALUE],
    )
    return numbers
