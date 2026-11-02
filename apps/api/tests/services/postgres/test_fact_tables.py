"""Facts, hypernodes and memberships (``ograg_fact_nodes``) on a real database: sharing, repeated keys, CASCADE and RESTRICT.

Skipped unless API_TEST_DATABASE_URL is set. See ``test_pg.py``.
"""

import hashlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import Table, delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from test_pg import URL, create_fresh_tables, run_async

from services.postgres.names import (
    CommonColumn,
    FactColumn,
    FactNodeColumn,
    HypernodeColumn,
    NumberColumn,
    RecordColumn,
)
from services.postgres.tables import Tables

pytestmark = pytest.mark.skipif(
    not URL,
    reason="set API_TEST_DATABASE_URL to a scratch Postgres with pgvector and pg_trgm",
)

RECORD_ID: str = "AG-1"
OTHER_RECORD_ID: str = "AG-2"
LANE: str = "fact"
PAYLOAD_KEY: str = "AssemblyGroup hasCharacteristic Characteristic payloadKg"
NAME_KEY: str = "AssemblyGroup name"
MISSING_ID: int = 999_999


@asynccontextmanager
async def open_fresh_tables() -> AsyncGenerator[tuple[AsyncEngine, Tables]]:
    engine: AsyncEngine = create_async_engine(URL)
    try:
        yield engine, await create_fresh_tables(engine)
    finally:
        await engine.dispose()


@asynccontextmanager
async def open_transaction() -> AsyncGenerator[tuple[AsyncConnection, Tables]]:
    """Fresh tables, and one transaction on them that is committed at the end."""
    async with open_fresh_tables() as (engine, tables), engine.begin() as conn:
        yield conn, tables


async def add_record(conn: AsyncConnection, tables: Tables, record_id: str) -> None:
    await conn.execute(
        insert(tables.records).values(
            {
                CommonColumn.ID: record_id,
                RecordColumn.CLS: "AssemblyGroup",
                RecordColumn.GRAPH: {},
                RecordColumn.INPUT: {},
                RecordColumn.ONTOLOGY_VERSION: "v0",
            }
        )
    )


async def add_fact(conn: AsyncConnection, tables: Tables, record_id: str) -> int:
    inserted = await conn.execute(
        insert(tables.facts)
        .values(
            {
                CommonColumn.RECORD_ID: record_id,
                CommonColumn.ANCHOR_ID: record_id,
                CommonColumn.LANE: LANE,
                FactColumn.PAIR_COUNT: 1,
                FactColumn.SORT_KEY: "x",
                CommonColumn.TEXT: "x",
                FactColumn.PAIRS: [],
            }
        )
        .returning(tables.facts.c[CommonColumn.ID])
    )
    return inserted.scalar_one()


async def add_hypernode(
    conn: AsyncConnection, tables: Tables, key: str, value: str
) -> int:
    inserted = await conn.execute(
        insert(tables.hypernodes)
        .values(
            {
                HypernodeColumn.KV_HASH: hashlib.sha256(
                    f"{key}\x00{value}".encode()
                ).hexdigest(),
                HypernodeColumn.KEY: key,
                CommonColumn.VALUE: value,
                HypernodeColumn.KEY_VID: "key-vid",
                HypernodeColumn.LEXICAL: False,
            }
        )
        .returning(tables.hypernodes.c[CommonColumn.ID])
    )
    return inserted.scalar_one()


async def add_membership(
    conn: AsyncConnection, tables: Tables, fact_id: int, node_id: int
) -> None:
    await conn.execute(
        insert(tables.fact_nodes).values(
            {
                CommonColumn.LANE: LANE,
                CommonColumn.NODE_ID: node_id,
                FactNodeColumn.FACT_ID: fact_id,
            }
        )
    )


async def get_node_ids(
    conn: AsyncConnection, tables: Tables, fact_id: int
) -> list[int]:
    found = await conn.execute(
        select(tables.fact_nodes.c[CommonColumn.NODE_ID])
        .where(tables.fact_nodes.c[FactNodeColumn.FACT_ID] == fact_id)
        .order_by(tables.fact_nodes.c[CommonColumn.NODE_ID])
    )
    return list(found.scalars())


async def count_rows(conn: AsyncConnection, table: Table) -> int:
    counted = await conn.execute(select(func.count()).select_from(table))
    return counted.scalar_one()


def test_a_fact_holds_several_hypernodes_with_the_same_key():
    async def run_check() -> None:
        async with open_transaction() as (conn, tables):
            await add_record(conn, tables, RECORD_ID)
            fact_id: int = await add_fact(conn, tables, RECORD_ID)
            light_id: int = await add_hypernode(conn, tables, PAYLOAD_KEY, "5")
            heavy_id: int = await add_hypernode(conn, tables, PAYLOAD_KEY, "12")
            await add_membership(conn, tables, fact_id, light_id)
            await add_membership(conn, tables, fact_id, heavy_id)

            assert await get_node_ids(conn, tables, fact_id) == [light_id, heavy_id]

    run_async(run_check)


def test_a_hypernode_is_shared_by_several_facts():
    async def run_check() -> None:
        async with open_transaction() as (conn, tables):
            await add_record(conn, tables, RECORD_ID)
            first_id: int = await add_fact(conn, tables, RECORD_ID)
            second_id: int = await add_fact(conn, tables, RECORD_ID)
            name_id: int = await add_hypernode(conn, tables, NAME_KEY, "Input tray")
            await add_membership(conn, tables, first_id, name_id)
            await add_membership(conn, tables, second_id, name_id)

            assert await get_node_ids(conn, tables, first_id) == [name_id]
            assert await get_node_ids(conn, tables, second_id) == [name_id]

    run_async(run_check)


def test_the_same_hypernode_cannot_join_a_fact_twice():
    async def run_check() -> None:
        async with open_fresh_tables() as (engine, tables):
            async with engine.begin() as conn:
                await add_record(conn, tables, RECORD_ID)
                fact_id: int = await add_fact(conn, tables, RECORD_ID)
                node_id: int = await add_hypernode(conn, tables, NAME_KEY, "Input tray")
                await add_membership(conn, tables, fact_id, node_id)

            with pytest.raises(IntegrityError):
                async with engine.begin() as conn:
                    await add_membership(conn, tables, fact_id, node_id)

    run_async(run_check)


def test_memberships_need_an_existing_fact_and_hypernode():
    async def run_check() -> None:
        async with open_fresh_tables() as (engine, tables):
            async with engine.begin() as conn:
                await add_record(conn, tables, RECORD_ID)
                fact_id: int = await add_fact(conn, tables, RECORD_ID)
                node_id: int = await add_hypernode(conn, tables, NAME_KEY, "Input tray")

            with pytest.raises(IntegrityError):
                async with engine.begin() as conn:
                    await add_membership(conn, tables, MISSING_ID, node_id)
            with pytest.raises(IntegrityError):
                async with engine.begin() as conn:
                    await add_membership(conn, tables, fact_id, MISSING_ID)

    run_async(run_check)


def test_deleting_a_fact_removes_its_memberships_and_keeps_hypernodes():
    async def run_check() -> None:
        async with open_transaction() as (conn, tables):
            await add_record(conn, tables, RECORD_ID)
            gone_id: int = await add_fact(conn, tables, RECORD_ID)
            kept_id: int = await add_fact(conn, tables, RECORD_ID)
            name_id: int = await add_hypernode(conn, tables, NAME_KEY, "Input tray")
            payload_id: int = await add_hypernode(conn, tables, PAYLOAD_KEY, "5")
            await add_membership(conn, tables, gone_id, name_id)
            await add_membership(conn, tables, gone_id, payload_id)
            await add_membership(conn, tables, kept_id, name_id)

            await conn.execute(
                delete(tables.facts).where(tables.facts.c[CommonColumn.ID] == gone_id)
            )

            assert await get_node_ids(conn, tables, gone_id) == []
            assert await get_node_ids(conn, tables, kept_id) == [name_id]
            assert await count_rows(conn, tables.hypernodes) == 2  # now unused

    run_async(run_check)


def test_deleting_a_record_cascades_to_its_facts_memberships_and_numbers():
    async def run_check() -> None:
        async with open_transaction() as (conn, tables):
            for record_id in (RECORD_ID, OTHER_RECORD_ID):
                await add_record(conn, tables, record_id)
            fact_id: int = await add_fact(conn, tables, RECORD_ID)
            other_fact_id: int = await add_fact(conn, tables, OTHER_RECORD_ID)
            name_id: int = await add_hypernode(conn, tables, NAME_KEY, "Input tray")
            await add_membership(conn, tables, fact_id, name_id)
            await add_membership(conn, tables, other_fact_id, name_id)
            for record_id in (RECORD_ID, OTHER_RECORD_ID):
                await conn.execute(
                    insert(tables.numbers).values(
                        {
                            CommonColumn.RECORD_ID: record_id,
                            CommonColumn.ANCHOR_ID: record_id,
                            NumberColumn.PATH: "Characteristic.payloadKg",
                            CommonColumn.VALUE: 12.0,
                        }
                    )
                )

            await conn.execute(
                delete(tables.records).where(
                    tables.records.c[CommonColumn.ID] == RECORD_ID
                )
            )

            assert await count_rows(conn, tables.facts) == 1
            assert await get_node_ids(conn, tables, fact_id) == []
            assert await get_node_ids(conn, tables, other_fact_id) == [name_id]
            assert await count_rows(conn, tables.numbers) == 1
            assert await count_rows(conn, tables.hypernodes) == 1  # still there

    run_async(run_check)


def test_a_hypernode_in_use_cannot_be_deleted_but_a_floating_one_can():
    async def run_check() -> None:
        async with open_fresh_tables() as (engine, tables):
            async with engine.begin() as conn:
                await add_record(conn, tables, RECORD_ID)
                fact_id: int = await add_fact(conn, tables, RECORD_ID)
                used_id: int = await add_hypernode(conn, tables, NAME_KEY, "Input tray")
                floating_id: int = await add_hypernode(conn, tables, PAYLOAD_KEY, "5")
                await add_membership(conn, tables, fact_id, used_id)

            with pytest.raises(IntegrityError):
                async with engine.begin() as conn:
                    await conn.execute(
                        delete(tables.hypernodes).where(
                            tables.hypernodes.c[CommonColumn.ID] == used_id
                        )
                    )

            async with engine.begin() as conn:
                await conn.execute(
                    delete(tables.hypernodes).where(
                        tables.hypernodes.c[CommonColumn.ID] == floating_id
                    )
                )
                await conn.execute(
                    delete(tables.facts).where(
                        tables.facts.c[CommonColumn.ID] == fact_id
                    )
                )
                await conn.execute(  # its fact is gone: now it is floating too
                    delete(tables.hypernodes).where(
                        tables.hypernodes.c[CommonColumn.ID] == used_id
                    )
                )

                assert await count_rows(conn, tables.hypernodes) == 0

    run_async(run_check)
