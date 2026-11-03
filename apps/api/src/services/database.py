from __future__ import annotations

from typing import Any

type Tx = Any
"""Unit of work (e.g. ``AsyncSession``), passed to stores. ``None``: no transaction."""


class ConflictError(RuntimeError):
    """Write collided with concurrent one"""


class UnstorableValueError(ValueError):
    """A store cannot save a value"""
