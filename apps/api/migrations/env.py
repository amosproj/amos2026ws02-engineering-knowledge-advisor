"""Alembic environment: migrates ``db.ModelBase.metadata`` (the OG-RAG tables included) on ``API_DATABASE_URL``.

Runs synchronously: the psycopg driver of the async URL works without asyncio too.

https://alembic.sqlalchemy.org/en/latest/autogenerate.html

**WARNING:** renamed columns autogen as DROP + ADD => data loss.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Engine, create_engine, pool

from config.settings import get_settings
from db import ModelBase, get_ograg_tables
from db.session import get_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

get_ograg_tables()  # registers the OG-RAG tables on the metadata
target_metadata = ModelBase.metadata
URL = config.get_main_option("sqlalchemy.url") or get_database_url(get_settings())


def run_migrations_offline() -> None:
    """Emit SQL instead of running it (``alembic upgrade head --sql``)."""
    context.configure(url=URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine: Engine = create_engine(URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
