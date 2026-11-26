from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from sqlalchemy import CursorResult, delete, func, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from test_pg import URL, create_fresh_tables, run_async

from config.settings import get_schema_settings
from db import (
    CommonColumn,
    FactColumn,
    FactModel,
    FactNodeColumn,
    FactNodeModel,
    HypernodeColumn,
    HypernodeModel,
    ModelBase,
    RecordColumn,
    RecordModel,
    TableName,
    VectorColumn,
    VectorModel,
)
from services import Lane, VectorKind

pytestmark = pytest.mark.skipif(
    not URL,
    reason="set API_TEST_DATABASE_URL to a scratch Postgres",
)

RECORD_ID: str = "AG-1"
OTHER_RECORD_ID: str = "AG-2"
NAME_KEY: str = "AssemblyGroup name"
MODEL: str = "fastembed:intfloat/multilingual-e5-base"


def to_id(text: str) -> UUID:
    return uuid5(NAMESPACE_URL, text)


@asynccontextmanager
async def open_fresh_tables() -> AsyncGenerator[AsyncEngine]:
    engine: AsyncEngine = create_async_engine(URL)
    try:
        await create_fresh_tables(engine)
        yield engine
    finally:
        await engine.dispose()


async def add_record(conn: AsyncConnection, record_id: str) -> None:
    await conn.execute(
        insert(RecordModel).values(
            {
                CommonColumn.ID: record_id,
                RecordColumn.CLS: "AssemblyGroup",
                RecordColumn.GRAPH: {},
                RecordColumn.INPUT: {},
                RecordColumn.ONTOLOGY_VERSION: "v0",
            }
        )
    )


async def add_fact(conn: AsyncConnection, record_id: str) -> int:
    inserted: CursorResult = await conn.execute(
        insert(FactModel)
        .values(
            {
                CommonColumn.RECORD_ID: record_id,
                CommonColumn.ANCHOR_ID: record_id,
                CommonColumn.LANE: Lane.FACT,
                FactColumn.SORT_KEY: "123",
                FactColumn.TEXT: "asdf",
            }
        )
        .returning(FactModel.id)
    )
    return inserted.scalar_one()


async def add_hypernode(conn: AsyncConnection, value: str) -> UUID:
    """Adds a ``NAME_KEY`` hypernode, its id is ``uuid5`` of key and ``value``."""
    node_id: UUID = to_id(f"{NAME_KEY}\x00{value}")
    await conn.execute(
        insert(HypernodeModel).values(
            {
                CommonColumn.ID: node_id,
                HypernodeColumn.KEY: NAME_KEY,
                CommonColumn.VALUE: value,
                HypernodeColumn.KEY_VID: to_id(NAME_KEY),
                HypernodeColumn.LEXICAL: False,
            }
        )
    )
    return node_id


async def add_membership(conn: AsyncConnection, fact_id: int, node_id: UUID) -> None:
    await conn.execute(
        insert(FactNodeModel).values(
            {
                CommonColumn.LANE: Lane.FACT,
                CommonColumn.NODE_ID: node_id,
                FactNodeColumn.FACT_ID: fact_id,
                CommonColumn.POSITION: 0,
            }
        )
    )


async def add_vector(conn: AsyncConnection, dimensions: int) -> None:
    await conn.execute(
        insert(VectorModel).values(
            {
                VectorColumn.KIND: VectorKind.VALUE,
                CommonColumn.ID: to_id(f"vector {dimensions}"),
                VectorColumn.MODEL: MODEL,
                # vec [1.0, 0.0, 0.0, ..., 0.0]
                VectorColumn.EMBEDDING: [1.0] + [0.0] * (dimensions - 1),
            }
        )
    )


async def count_rows(conn: AsyncConnection, model: type[ModelBase]) -> int:
    counted: CursorResult = await conn.execute(select(func.count()).select_from(model))
    return counted.scalar_one()


async def get_index_definition(conn: AsyncConnection, name: str) -> str:
    definition: str | None = await conn.scalar(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
        {"name": name},
    )
    assert definition is not None, f"no index {name}"
    return definition.lower()


def test_deleting_record_cascades_bound_facts_and_memberships():
    async def run_check() -> None:
        async with open_fresh_tables() as engine, engine.begin() as conn:
            # add two records
            for record_id in (RECORD_ID, OTHER_RECORD_ID):
                await add_record(conn, record_id)

            # add two facts cut from both records
            fact_id: int = await add_fact(conn, RECORD_ID)
            other_fact_id: int = await add_fact(conn, OTHER_RECORD_ID)

            # add shared hypernode
            node_id: UUID = await add_hypernode(conn, "Input tray")

            # connect hypernode with facts
            await add_membership(conn, fact_id, node_id)
            await add_membership(conn, other_fact_id, node_id)

            await conn.execute(delete(RecordModel).where(RecordModel.id == RECORD_ID))

            assert await count_rows(conn, FactModel) == 1
            # only shared hypernode remains
            assert await count_rows(conn, FactNodeModel) == 1
            assert await count_rows(conn, HypernodeModel) == 1

    run_async(run_check)


def test_cannot_delete_hypernode_in_use():
    async def run_check() -> None:
        async with open_fresh_tables() as engine:
            async with engine.begin() as conn:
                await add_record(conn, RECORD_ID)
                fact_id: int = await add_fact(conn, RECORD_ID)
                node_id: UUID = await add_hypernode(conn, "Input tray")
                await add_membership(conn, fact_id, node_id)

            with pytest.raises(IntegrityError):
                async with engine.begin() as conn:
                    await conn.execute(
                        delete(HypernodeModel).where(HypernodeModel.id == node_id)
                    )

    run_async(run_check)


def test_vectors_embedding_size():
    async def run_check() -> None:
        dimensions: int = get_schema_settings().embedding_dimensions
        async with open_fresh_tables() as engine:
            async with engine.begin() as conn:
                await add_vector(conn, dimensions)

            with pytest.raises(DBAPIError):
                async with engine.begin() as conn:
                    await add_vector(conn, dimensions - 1)

    run_async(run_check)


def test_all_vector_kinds_have_cosine_hnsw_index():
    async def run_check() -> None:
        async with open_fresh_tables() as engine, engine.connect() as conn:
            for kind in VectorKind:
                definition: str = await get_index_definition(
                    conn, f"{TableName.VECTORS}_{kind}_hnsw"
                )
                assert "using hnsw" in definition
                assert "vector_cosine_ops" in definition
                assert f"'{kind}'" in definition

    run_async(run_check)


def test_only_lexical_hypernode_values_have_trigram_index():
    async def run_check() -> None:
        async with open_fresh_tables() as engine, engine.connect() as conn:
            definition: str = await get_index_definition(
                conn, f"{TableName.HYPERNODES}_value_trgm"
            )
            assert "using gin" in definition
            assert "gin_trgm_ops" in definition
            assert "where lexical" in definition

    run_async(run_check)
