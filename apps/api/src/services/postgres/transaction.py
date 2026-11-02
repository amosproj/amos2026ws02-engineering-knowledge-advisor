from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager

from sqlalchemy.exc import DataError, DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from services import ConflictError, UnstorableValueError

type PgTx = AsyncSession | AsyncConnection
BATCH_SIZE: int = 10_000
UNSTORABLE: str = "failed to store"
SQL_STATE = {  # https://www.postgresql.org/docs/current/errcodes-appendix.html
    "40P01": "deadlock_detected",
    "40001": "serialization_failure",
    "23503": "foreign_key_violation",
}
ERROR_BROKEN_CHARACTER: str = f"{UNSTORABLE}: text with a broken character"
ERROR_UNSTORABLE_VALUE: str = f"{UNSTORABLE}: {{detail}}"
ERROR_CONFLICT: str = "conflict ({condition}): {detail}"


def get_batches(ids: Sequence[str]) -> list[Sequence[str]]:
    return [ids[i : i + BATCH_SIZE] for i in range(0, len(ids), BATCH_SIZE)]


def _get_sqlstate(exc: DBAPIError) -> str | None:
    for error in [exc.orig, getattr(exc.orig, "__cause__", None)]:
        code: str | None = getattr(error, "sqlstate", None)
        if code:
            return code
    return None


def _get_first_line(exc: BaseException | None) -> str:
    """Returns error message without DETAIL or CONTEXT lines from Postgres. DETAIL can reveal internals."""
    text = str(exc).strip()
    return text.splitlines()[0] if text else type(exc).__name__


@asynccontextmanager
async def get_transaction(engine: AsyncEngine, tx: PgTx | None) -> AsyncGenerator[PgTx]:
    """Returns passed transaction, or opens a new connection.

    Raises:
        UnstorableValueError: SQLSTATE class 22xxx data exception, or text the driver cannot encode.
        ConflictError: deadlock, serialization failure or a foreign key violation by concurrent write.
    """
    try:
        if tx is not None:
            yield tx
        else:
            async with engine.begin() as conn:
                yield conn

    except UnicodeEncodeError as exc:
        raise UnstorableValueError(ERROR_BROKEN_CHARACTER) from exc

    except DataError as exc:
        raise UnstorableValueError(
            ERROR_UNSTORABLE_VALUE.format(detail=_get_first_line(exc.orig))
        ) from exc

    except (
        DBAPIError
    ) as exc:  # keep this under DataError, as DataError is subclass of DBAPIError
        code: str | None = _get_sqlstate(exc)
        if code in SQL_STATE:
            raise ConflictError(
                ERROR_CONFLICT.format(
                    condition=SQL_STATE[code], detail=_get_first_line(exc.orig)
                )
            ) from exc
        raise
