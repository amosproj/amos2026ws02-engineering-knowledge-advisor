from __future__ import annotations

from abc import abstractmethod
from enum import StrEnum
from typing import Protocol
from uuid import UUID

import numpy as np

from services.database import Tx


class VectorKind(StrEnum):
    """The vector kinds a ``VectorStore`` holds. Members are plain strings."""

    KEY = "key"
    """Keys of hypernodes, e.g. ``"AssemblyGroup name"``."""
    VALUE = "value"
    """Values of hypernodes, e.g. ``"Input tray"``."""


class VectorStore(Protocol):
    """Store that writes and reads vectors / embeddings.

    Vectors are grouped by ``kind``. Keep the kinds apart, e.g. one index per kind.
    An existing id never needs to be overwritten. Each vector keeps the name of the embedding model that made it.
    """

    @abstractmethod
    async def upsert_vectors(
        self,
        kind: VectorKind,
        model: str,
        ids: list[UUID],
        vectors: np.ndarray,
        tx: Tx | None = None,
    ) -> None:
        """Stores ``vectors`` by id. An id that is already stored may be left as it is.

        Args:
            kind: see ``VectorKind``.
            model: name of the embedding model that made ``vectors`` (``EmbeddingService.name``).
            ids: one id per vector.
            vectors: ``len(ids)``-many L2-normalised float32 rows / embeddings.
            tx: transaction, or ``None``.
        """
        ...

    @abstractmethod
    async def delete_vectors(self, kind: VectorKind, ids: list[UUID]) -> None:
        """Deletes vectors by id. Ids that are not stored are ignored."""
        ...

    @abstractmethod
    async def search_vectors(
        self, kind: VectorKind, vector: np.ndarray, k: int
    ) -> list[tuple[UUID, float]]:
        """Returns the nearest vectors of ``kind``.

        Args:
            kind: see ``VectorKind``.
            vector: L2-normalised query embedding.
            k: how many to return.

        Returns:
            Up to ``k`` (id, cosine similarity) tuples, best first. Approximate search (HNSW) is fine.
        """
        ...
