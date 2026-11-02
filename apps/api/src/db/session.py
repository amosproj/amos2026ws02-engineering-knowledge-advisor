from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from config.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url.get_secret_value(), pool_pre_ping=True
    )


def get_session() -> Generator[Session]:
    with Session(get_engine()) as session:
        yield session
