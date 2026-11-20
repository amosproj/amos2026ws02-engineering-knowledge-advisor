from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncConnection

from db import TableName, Tables

EXTENSIONS: tuple[str, ...] = ("vector", "pg_trgm")
S3_ENV: dict[str, str] = {
    "API_S3_ENDPOINT_URL": "http://localhost:9000",
    "API_S3_BUCKET": "test",
    "API_S3_ACCESS_KEY": "test",
    "API_S3_SECRET_KEY": "test",
    "API_S3_REGION": "us-east-1",
    "API_S3_PUBLIC_URL": "/storage",
}


def assert_mentions(text: str, *words: str) -> None:
    """Asserts that ``text`` contains each of ``words`` (case ignore)."""
    missing: list[str] = [
        word for word in words if word.casefold() not in text.casefold()
    ]
    assert not missing, f"{missing} not in {text!r}"


async def recreate_tables(conn: AsyncConnection, tables: Tables) -> None:
    """Drops all tables of ``TableName`` and creates ``tables`` with all extensions."""
    for name in TableName:
        await conn.execute(sql(f'DROP TABLE IF EXISTS "{name}" CASCADE'))
    for extension in EXTENSIONS:
        await conn.execute(sql(f"CREATE EXTENSION IF NOT EXISTS {extension}"))
    await conn.run_sync(tables.metadata.create_all)
