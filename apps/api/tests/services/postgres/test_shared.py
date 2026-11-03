import asyncio
from collections.abc import Mapping
from typing import Any, cast

import pytest
from sqlalchemy import Column, Integer, MetaData, Select, String, Table, select
from sqlalchemy.dialects.postgresql import Insert, psycopg
from sqlalchemy.sql import ClauseElement
from sqlalchemy.sql.compiler import SQLCompiler

from services.postgres import transaction
from services.postgres.shared import Conditions, Statements
from services.postgres.transaction import PgTx

TABLE = Table(
    "items",
    MetaData(),
    Column("id", String, primary_key=True),
    Column("position", Integer, nullable=False),
)
# more values than the 65535 parameters Postgres allows per statement
MANY_IDS: list[str] = [f"R-{n}" for n in range(70_000)]
ROWS: list[dict[str, Any]] = [
    {"id": rec_id, "position": position} for position, rec_id in enumerate(MANY_IDS)
]
FEW_IDS: list[str] = ["R-1", "R-2", "R-3", "R-4", "R-5"]


class RecordingConnection:
    """Stands in for a connection: keeps the executed statements instead of running them."""

    def __init__(self):
        self.statements: list[ClauseElement] = []

    async def execute(self, stmt: ClauseElement) -> None:
        self.statements.append(stmt)


def compile_statement(stmt: ClauseElement) -> SQLCompiler:
    return cast(SQLCompiler, stmt.compile(dialect=psycopg.dialect()))


def compile_where(values: list[str]) -> SQLCompiler:
    stmt: Select[Any] = select(TABLE.c.id).where(
        Conditions.match_any(TABLE.c.id, values)
    )
    return compile_statement(stmt)


def compile_insert(rows: list[dict[str, Any]]) -> SQLCompiler:
    return compile_statement(Statements.build_unnest_insert(TABLE, rows))


# ---- Conditions.match_any ----------------------------------------------------------


@pytest.mark.parametrize("values", [[], ["R-1"], MANY_IDS])
def test_match_any_sends_one_array_parameter(values: list[str]):
    compiled: SQLCompiler = compile_where(values)
    params: Mapping[str, Any] = compiled.params
    assert "= ANY (" in str(compiled)
    assert list(params.values()) == [values]


def test_match_any_sql_is_the_same_for_every_list_length():
    assert str(compile_where(["R-1"])) == str(compile_where(MANY_IDS))


# ---- Statements.build_unnest_insert ------------------------------------------------


@pytest.mark.parametrize("rows", [ROWS[:1], ROWS])
def test_unnest_insert_sends_one_array_per_column(rows: list[dict[str, Any]]):
    compiled: SQLCompiler = compile_insert(rows)
    params: Mapping[str, Any] = compiled.params
    sql: str = str(compiled)
    assert sql.startswith("INSERT INTO items (id, position) SELECT")
    assert "FROM unnest(" in sql
    assert list(params.values()) == [
        [row["id"] for row in rows],
        [row["position"] for row in rows],
    ]


def test_unnest_insert_sql_is_the_same_for_every_row_count():
    assert str(compile_insert(ROWS[:1])) == str(compile_insert(ROWS))


def test_unnest_insert_takes_on_conflict_and_returning():
    stmt: Insert = Statements.build_unnest_insert(TABLE, ROWS[:1])
    sql: str = str(
        compile_statement(
            stmt.on_conflict_do_nothing(index_elements=[TABLE.c.id]).returning(
                TABLE.c.id
            )
        )
    )
    assert sql.endswith("ON CONFLICT (id) DO NOTHING RETURNING items.id")


def test_unnest_insert_refuses_no_rows():
    with pytest.raises(ValueError):
        Statements.build_unnest_insert(TABLE, [])


# ---- Statements.delete_matching ----------------------------------------------------


def test_delete_matching_runs_one_delete_per_batch(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(transaction, "BATCH_SIZE", 2)
    conn = RecordingConnection()
    asyncio.run(Statements.delete_matching(cast(PgTx, conn), TABLE.c.id, FEW_IDS))
    compiled: list[SQLCompiler] = [compile_statement(stmt) for stmt in conn.statements]
    assert {str(statement) for statement in compiled} == {
        "DELETE FROM items WHERE items.id = ANY (%(param_1)s::VARCHAR[])"
    }
    assert [list(statement.params.values()) for statement in compiled] == [
        [["R-1", "R-2"]],
        [["R-3", "R-4"]],
        [["R-5"]],
    ]


def test_delete_matching_runs_nothing_without_values():
    conn = RecordingConnection()
    asyncio.run(Statements.delete_matching(cast(PgTx, conn), TABLE.c.id, []))
    assert conn.statements == []
