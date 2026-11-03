from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import (
    ARRAY,
    BindParameter,
    Column,
    ColumnElement,
    Table,
    TableValuedAlias,
    any_,
    bindparam,
    delete,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import Insert, insert

from services.postgres.transaction import PgTx, get_batches

ERROR_NO_ROWS: str = "no rows to insert"


class Conditions:
    @staticmethod
    def match_any[T](column: Column[T], values: Sequence[T]) -> ColumnElement[bool]:
        """Returns a ``column = ANY(:values)`` condition.

        ``column = ANY(:values)`` sends one array param.
        ``column.in_(values)`` sends one param per value.
        Postgres uses index of ``column`` in both cases.

        Args:
            column: column to compare.
            values: values to match, may be thousands.
        """
        values_param: BindParameter = bindparam(
            key=None, value=list(values), type_=ARRAY(column.type)
        )
        return column == any_(values_param)


class Statements:
    @staticmethod
    def build_unnest_insert(table: Table, rows: Sequence[Mapping[str, Any]]) -> Insert:
        """Returns a ``INSERT ... SELECT FROM unnest(:col1, :col2, ...)`` statement for ``rows``.

        Above version sends one array param per column.
        ``conn.execute(insert(table), rows)`` runs one ``INSERT`` per row.
        The result is Postgres' ``Insert``: ``.on_conflict_do_nothing(...)`` and ``.returning(...)`` can be added.

        Args:
            table: table for insertion.
            rows: column name -> value, the same columns in every row, may be thousands.

        Raises:
            ValueError: empty ``rows`` not allowed.
        """
        if not rows:
            raise ValueError(ERROR_NO_ROWS)

        columns: list[Column[Any]] = [table.c[name] for name in rows[0]]
        arrays: list[BindParameter[Any]] = [
            bindparam(
                key=None, value=[row[col.name] for row in rows], type_=ARRAY(col.type)
            )
            for col in columns
        ]
        unnested: TableValuedAlias = (
            func.unnest(*arrays)
            .table_valued(*(col.name for col in columns))
            .render_derived()
        )
        return insert(table).from_select(columns, select(*unnested.c))

    @staticmethod
    async def delete_matching(
        conn: PgTx, column: Column[Any], values: Sequence[str]
    ) -> None:
        """Deletes rows from ``column``'s table if row's ``column`` holds one of ``values``.

        Args:
            conn: connection of current transaction.
            column: column to match.
            values: values to match, may be thousands.
        """
        for batch in get_batches(values):
            await conn.execute(
                delete(column.table).where(Conditions.match_any(column, batch))
            )
