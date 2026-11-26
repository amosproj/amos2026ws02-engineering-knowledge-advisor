from collections.abc import Mapping, Sequence

from sqlalchemy import (
    ARRAY,
    BindParameter,
    Column,
    ColumnElement,
    Executable,
    Table,
    TableValuedAlias,
    any_,
    bindparam,
    delete,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.orm import QueryableAttribute

from services import Tx
from services.postgres.transaction import get_batches

ERROR_NO_ROWS: str = "no rows to insert"


class Conditions:
    @staticmethod
    def match_any[T](
        column: QueryableAttribute[T] | ColumnElement[T], values: Sequence[T]
    ) -> ColumnElement[bool]:
        """Returns a ``column = ANY(:values)`` condition.

        ``column = ANY(:values)`` sends one array param.
        ``column.in_(values)`` sends one param per value.
        Postgres uses index of ``column`` in both cases.

        Args:
            column: column to compare.
            values: values to match, may be thousands.
        """
        expression: ColumnElement[T] = column.expression
        values_param: BindParameter = bindparam(
            key=None, value=list(values), type_=ARRAY(expression.type)
        )
        return expression == any_(values_param)


class Statements:
    @staticmethod
    def overwrite_loaded[S: Executable](stmt: S) -> S:
        """Returns ``stmt`` set to overwrite objects the session already loaded (``populate_existing``)."""
        return stmt.execution_options(populate_existing=True)

    @staticmethod
    def build_unnest_insert(
        table: Table, rows: Sequence[Mapping[str, object]]
    ) -> Insert:
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

        columns: list[Column[object]] = [table.c[name] for name in rows[0]]
        arrays: list[BindParameter[Sequence[object]]] = [
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
        session: Tx,
        table: Table,
        column: QueryableAttribute[str] | ColumnElement[str],
        values: Sequence[str],
    ) -> None:
        """Deletes rows from ``table`` if row's ``column`` holds one of ``values``.

        Args:
            session: session of current transaction.
            table: table to delete from.
            column: column to match.
            values: values to match, may be thousands.
        """
        for batch in get_batches(values):
            await session.execute(
                delete(table).where(Conditions.match_any(column, batch))
            )
