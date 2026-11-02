from __future__ import annotations

from abc import abstractmethod
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    """Embeds texts into vectors with an embedding model.

    Attributes:
        name: e.g. ``"fastembed:BAAI/bge-small-en-v1.5"``. Part of vector ids. New embedding model necessitates re-running embedding.
              Similarity thresholds depend on the model, recalibrate when embedding model changes.
    """

    name: str

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Embeds ``texts``, may be thousands.

        Note: run CPU-bound models in a worker thread.

        Returns:
            L2-normalised float32 row per text, in order. Dot product is cosine similarity.
        """
        ...

    @abstractmethod
    async def embed_query(self, text: str) -> np.ndarray:
        """Embeds a search query (some models embed queries differently from documents).

        Returns:
            L2-normalised float32 vector.
        """
        ...
