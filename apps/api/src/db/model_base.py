from functools import lru_cache

from sqlalchemy.orm import DeclarativeBase

from config.settings import get_settings
from services.postgres.tables import Tables, define_tables


class ModelBase(DeclarativeBase):
    """Declarative base of the backend's models. ``ModelBase.metadata`` is what Alembic migrates."""


@lru_cache
def get_ograg_tables() -> Tables:
    """Register OG-RAG tables on ``ModelBase.metadata``. Call this before using the metadata."""
    return define_tables(get_settings().ograg_embed_dim, ModelBase.metadata)
