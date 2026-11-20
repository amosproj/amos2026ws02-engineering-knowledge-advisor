from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from config.settings import SearchSettings
from services.database import Tx
from services.hypergraph import FactView
from services.records import Record


class SearchMode(StrEnum):
    """How a property's values are searched (``og:search``). Members are plain strings."""

    SEMANTIC = "semantic"
    """By meaning (embeddings). Default for text."""
    LEXICAL = "lexical"
    """By spelling (``pg_trgm``). For identifiers and codes."""
    FILTER = "filter"
    """As a number for filters. Default for numbers."""


@dataclass
class Retrieval:
    """Knowledge retrieval result.

    Attributes:
        facts: retrieved context in set-cover order.
        best_similarity: best semantic similarity to the query of any hypernode.
        best_lexical: best spelling similarity to the query of a ``lexical`` value.
    """

    facts: list[FactView]
    best_similarity: float
    best_lexical: float = 0.0


class KnowledgeIndex(Protocol):
    """Writes and reads the knowledge hypergraph. Call to keep in sync with stored records."""

    @abstractmethod
    async def write_records(
        self,
        records: Sequence[Record],
        deleted_ids: Sequence[str],
        tx: Tx | None = None,
    ) -> None:
        """Indexes ``records`` and drops records of ``deleted_ids``, including everything that depends on them.

        Args:
            records: the records to index.
            deleted_ids: records that were previously deleted, their facts are dropped, facts that copy or anchor to them are rebuilt.
            tx: transaction, or ``None``.
        """
        ...

    @abstractmethod
    async def retrieve_facts(self, query: str, settings: SearchSettings) -> Retrieval:
        """Returns the facts for ``query``. Hypernodes by meaning and spelling, then a greedy set cover.

        Args:
            query: search request.
            settings: search query settings.
        """
        ...
