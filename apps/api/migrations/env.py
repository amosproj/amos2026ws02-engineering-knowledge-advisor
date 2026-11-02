import logging

from alembic import context

from db import Base, get_engine

logging.basicConfig(level=logging.INFO)

with get_engine().connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)

    with context.begin_transaction():
        context.run_migrations()
