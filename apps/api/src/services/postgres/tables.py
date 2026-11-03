from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import (
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

from services.postgres.names import (
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
