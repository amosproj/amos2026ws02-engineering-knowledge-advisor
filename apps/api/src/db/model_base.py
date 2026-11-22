from functools import lru_cache

from sqlalchemy.orm import DeclarativeBase

from db.tables import Tables, define_tables


class ModelBase(DeclarativeBase):
    """Declarative base of the backend's models. ``ModelBase.metadata`` is what Alembic migrates."""


@lru_cache
def get_tables(embedding_dimensions: int) -> Tables:
    """Register tables on ``ModelBase.metadata``. Call this before using the metadata.

    Args:
        embedding_dimensions: embedding model vector dimensionality.
    """
    return define_tables(embedding_dimensions, ModelBase.metadata)
