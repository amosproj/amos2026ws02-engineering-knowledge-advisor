from __future__ import annotations

from abc import abstractmethod
from typing import Protocol

import numpy as np


class EmbeddingService(Protocol):
    """Embeds natural language texts into vectors.

    Attributes:
        name: embedding model identifier, e.g. ``"fastembed:intfloat/multilingual-e5-base"``.
              Stored with every vector and part of vector ids. New embedding model requires re-running embedding.
    """

    name: str

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Embeds ``texts``. Adds model's text prefix if required (e5: ``"passage: "``).

        Note: run CPU-bound models in a worker thread.

        Returns:
            L2-normalised float32 vector per text. Dot product is cosine similarity.
        """
        ...

    @abstractmethod
    async def embed_query(self, query_text: str) -> np.ndarray:
        """Embeds a ``query_text``. Adds model's query prefix if required (e5: ``"query: "``).

        Returns:
            L2-normalised float32 vector.
        """
        ...
