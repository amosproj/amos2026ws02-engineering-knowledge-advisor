from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from services.database import Tx
from services.graph import FactView, Filter
from services.records import Record


class SearchMode(StrEnum):
    """How a property's values are searched (``og:search``). Members are plain strings."""

    SEMANTIC = "semantic"
    """By meaning (embeddings). Default for text."""
    LEXICAL = "lexical"
    """By spelling (``pg_trgm``). For identifiers and names."""
    FILTER = "filter"
    """As a number for filters. Default for numbers."""


@dataclass(frozen=True)
class SearchSettings:
    """Settings for knowledge search.

    Note: similarity thresholds depend on the embedding model.

    Attributes:
        top_k: hypernodes taken by value and by key similarity (``k``).
        max_edges: facts (hyperedges) in the context given to the LLM (``L``).
        candidate_pool: value hits fetched from the vector store per query.
        min_similarity: Gate 1: similarity a request needs to be answered at all.
        max_matches: entities listed in ``SearchResult.matches``.
        rules_min_similarity: rule's similarity needed to be reviewed.
        rules_answer_min_similarity: rule's similarity to the request needed to answer a refused request.
        rules_top_k: rules the review sees at most.
        rules_max_fact_queries: cited facts used as extra queries for rules.
        guideline_fallback: allow ``answered_by_guideline``. If ``False``: guidelines reviewed and listed, but do not directly answer the query.
        hub_limit: hypernode in more facts than this adds no candidate facts of its own. It only counts for facts found through other hypernodes.
        lexical_min_similarity: value of a ``lexical`` property this close in spelling to the request is a candidate, and opens Gate 1.
        filter_pool_factor: with filters, this many times more hits are fetched.
                            Filters are applied after the vector search, so a restrictive filter could otherwise leave no candidates.
    """

    top_k: int = 10
    max_edges: int = 8
    candidate_pool: int = 50
    min_similarity: float = 0.72
    max_matches: int = 5
    rules_min_similarity: float = 0.65
    rules_answer_min_similarity: float = 0.761
    rules_top_k: int = 12
    rules_max_fact_queries: int = 5
    guideline_fallback: bool = True
    hub_limit: int = 1000
    lexical_min_similarity: float = 0.6
    filter_pool_factor: int = 10


@dataclass
class Retrieval:
    """Knowledge retrieval result.

    Attributes:
        facts: the context, in set-cover order.
        best_similarity: best semantic similarity of any hypernode to the query (Gate 1).
        scores_by_anchor_id: anchor record id -> best similarity among its facts' hypernodes (hubs left out).
        best_lexical: best spelling similarity of a ``lexical`` value to the query (Gate 1).
    """

    facts: list[FactView]
    best_similarity: float
    scores_by_anchor_id: dict[str, float]
    best_lexical: float = 0.0


@dataclass(frozen=True)
class MaintenanceReport:
    """Result of knowledge maintenance.

    Attributes:
        embedded: texts embedded that previously had no vector (e.g. embedder failed during write).
        deleted_vectors: vectors deleted that were not used in any hypernode.
        pruned_nodes: hypernodes deleted that were not used in any fact.
        stale_records: records validated with another ontology version. This requires a migration run, or a worker is running old version.
        ran: ``False`` when another process took over maintenance => nothing was done.
    """

    embedded: int
    deleted_vectors: int
    pruned_nodes: int
    stale_records: int = 0
    ran: bool = True


class KnowledgeIndex(Protocol):
    """Knowledge search service.

    Contract:
        - ``write_records`` runs in the record's transaction: after rollback the index is unchanged, after commit every process sees the change.
            Nothing is held in memory between requests.
        - ``retrieve_facts`` and ``get_rule_scores`` read committed data.
    """

    @abstractmethod
    async def lock_records(
        self, record_ids: Sequence[str], parent_ids: Sequence[str], tx: Tx | None = None
    ) -> None:
        """Reserves the locks for a write before it touches any row, held until ``tx`` finishes.

        If ``tx`` is ``None``, nothing is locked. Writes run sequentially whenever one writes a record another also writes or reads.

        Args:
            record_ids: records about to be written or deleted (exclusive lock, single write).
            parent_ids: parents whose identity values the write copies (shared lock, many read). Ids also in ``record_ids`` only get exclusive lock.
            tx: transaction, or ``None``.
        """
        ...

    @abstractmethod
    async def write_records(
        self,
        records: Sequence[Record],
        deleted_ids: Sequence[str],
        tx: Tx | None = None,
    ) -> None:
        """Indexes ``records`` and drops records of ``deleted_ids``, including everything that depends on them.

        Should survive an embedder failure. In this case ``maintain_index`` should try again to embed.

        Args:
            records: records to index.
            deleted_ids: ids of deleted records.
            tx: transaction, or ``None``.
        """
        ...

    @abstractmethod
    async def retrieve_facts(
        self, query: str, settings: SearchSettings, filters: Sequence[Filter] = ()
    ) -> Retrieval:
        """Returns the facts for ``query``. Hypernodes by meaning and spelling, then a greedy set cover.

        Args:
            query: search request.
            settings: search query settings.
            filters: keep only facts of anchors that satisfy all of these filters (and facts without an anchor).

        Returns:
            Knowledge context, the best similarities and scores per anchor record id.
        """
        ...

    @abstractmethod
    async def get_rule_scores(
        self, texts: Sequence[str], settings: SearchSettings
    ) -> list[dict[str, float]]:
        """Scores the guideline-lane records against each text.

        Args:
            texts: search request, answer, cited facts.
            settings: search query settings. Uses ``candidate_pool`` (hits per text) and ``hub_limit``

        Returns:
            Per text: record id -> best similarity of any of its values (records without a hit left out).
        """
        ...

    @abstractmethod
    async def maintain_index(self) -> MaintenanceReport:
        """Cleans up after writes. Embeds pending texts, and deletes unused vectors and hypernodes.

        Run periodically (e.g. every few minutes) and after an embedding outage, but never in the write path.
        """
        ...
