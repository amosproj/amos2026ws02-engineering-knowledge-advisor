from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

import numpy as np

from services.database import Tx


class VectorKind(StrEnum):
    """The vector kinds a ``VectorStore`` holds. Members are plain strings."""

    KEY = "key"
    """Keys of fact-lane hypernodes, e.g. ``"AssemblyGroup name"``."""
    VALUE = "value"
    """Values of fact-lane hypernodes, e.g. ``"Input tray"``."""
    RULE = "rule"
    """Values of hypernodes in the guideline lane."""


class VectorStore(Protocol):
    """Store that writes and reads vectors / embeddings.

    Vectors are grouped by ``kind``. Keep the kinds apart, e.g. one index per kind.
    An existing id never needs to be overwritten.
    ``get_existing_ids`` and ``upsert_vectors`` run in the write's transaction if given one.
    """

    @abstractmethod
    async def get_ids(self, kind: VectorKind) -> set[str]:
        """Returns all ids of ``kind``."""
        ...

    @abstractmethod
    async def get_existing_ids(
        self, kind: VectorKind, ids: Sequence[str], tx: Tx | None = None
    ) -> set[str]:
        """Returns which of ``ids`` are stored.

        Args:
            kind: see ``VectorKind``.
            ids: ids to check, may be thousands.
            tx: transaction, or ``None``.

        Returns:
            Stored ids.
        """
        ...

    @abstractmethod
    async def upsert_vectors(
        self,
        kind: VectorKind,
        ids: list[str],
        texts: list[str],
        vectors: np.ndarray,
        tx: Tx | None = None,
    ) -> None:
        """Stores ``vectors`` by id. An id that is already stored may be left as it is.

        Args:
            kind: see ``VectorKind``.
            ids: one id per vector.
            texts: original text per vector (debug only).
            vectors: ``len(ids)``-many L2-normalised float32 rows / embeddings.
            tx: transaction, or ``None``.
        """
        ...

    @abstractmethod
    async def delete_vectors(self, kind: VectorKind, ids: list[str]) -> None:
        """Deletes vectors by id. Ids that are not stored are ignored."""
        ...

    @abstractmethod
    async def search_vectors(
        self, kind: VectorKind, vector: np.ndarray, k: int
    ) -> list[tuple[str, float]]:
        """Returns the nearest vectors of ``kind``. Called several times per search request.

        Args:
            kind: see ``VectorKind``.
            vector: L2-normalised query embedding.
            k: how many to return, may be thousands.

        Returns:
            Up to ``k`` (id, cosine similarity) tuples, best first. Approximate search (HNSW) is fine.
        """
        ...
