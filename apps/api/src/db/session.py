from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.settings import Settings

ERROR_NO_DATABASE_URL: str = "API_DATABASE_URL is not set"


def get_database_url(settings: Settings) -> str:
    """
    Raises:
        ValueError: ``API_DATABASE_URL`` is not set.
    """
    if settings.database_url is None:
        raise ValueError(ERROR_NO_DATABASE_URL)
    return settings.database_url.get_secret_value()


def create_engine(settings: Settings) -> AsyncEngine:
    """The app's async engine. One per process.

    Raises:
        ValueError: ``API_DATABASE_URL`` is not set.
    """
    return create_async_engine(get_database_url(settings), pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Request's unit of work, an ``AsyncSession`` inside ``session.begin()``.

    Commits when route returns, rolls back when it raises.
    Use with ``Depends(get_session, scope="function")``: commits before response is sent => failing commit errors out
    """
    sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
    async with sessions() as session, session.begin():
        yield session
