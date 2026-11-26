from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

type Tx = AsyncSession
"""Unit of work (``AsyncSession``), passed to stores. ``None``: no transaction."""


class ConflictError(RuntimeError):
    """Write collided with concurrent one"""


class UnstorableValueError(ValueError):
    """A store cannot save a value"""
