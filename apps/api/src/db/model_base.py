from sqlalchemy import FromClause, Table
from sqlalchemy.orm import DeclarativeBase

ERROR_NOT_A_TABLE: str = "{model} is not mapped to a table"


class ModelBase(DeclarativeBase):
    """Declarative base of the backend's models. ``ModelBase.metadata`` is what Alembic migrates."""

    @classmethod
    def get_table(cls) -> Table:
        """Returns the table of this model."""
        table: FromClause = cls.__table__
        if not isinstance(table, Table):
            raise TypeError(ERROR_NOT_A_TABLE.format(model=cls.__name__))
        return table
