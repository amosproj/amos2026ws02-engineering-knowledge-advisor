from __future__ import annotations

from abc import abstractmethod
from collections.abc import Collection, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from services.database import Tx


class Lane(StrEnum):
    """The lane a record's facts take (``Ontology.get_lane``). Members are plain strings."""

    FACT = "fact"
    """Searched for as facts."""
    GUIDELINE = "guideline"
    """Checked against as guidelines."""


@dataclass(frozen=True)
class Filter:
    """Numeric filter on search results. Anchors whose numbers pass the filter should be kept, facts without an anchor too.

    Attributes:
        path: ``"Class.property"`` path of a ``filter`` property, e.g. ``"Characteristic.payloadKg"``.
        op: ``eq``, ``lt``, ``lte``, ``gt`` or ``gte``.
        value: comparison value.
    """

    path: str
    op: Literal["eq", "lt", "lte", "gt", "gte"]
    value: float


@dataclass(frozen=True)
class NumberRow:
    """A record's number. One row per anchor. See ``Filter``.

    Attributes:
        record_id: record it was read from.
        anchor_id: id of anchor record the record's facts belong to.
        path: ``"Class.property"``
        value: value of number
    """

    record_id: str
    anchor_id: str
    path: str
    value: float


@dataclass(frozen=True)
class Hypernode:
    """``key: value`` pair shared by every fact containing it.

    Attributes:
        id: store-assigned id, stable while the hypernode exists.
        key: e.g. ``"AssemblyGroup name"``
        value: e.g. ``"Input tray"``
        key_vid: vector id of the key's text (kind ``key``).
        value_vid: vector id of the value (kind ``value``, or ``rule``). ``None`` for no semantic search.
        lexical: whether spelling search should also be used.
    """

    id: int
    key: str
    value: str
    key_vid: str
    value_vid: str | None
    lexical: bool = False


@dataclass(frozen=True)
class HypernodeSpec:
    """Hypernode as a write describes it without an id: store reuses stored one with the same key and value, or creates it.

    Attributes: see ``Hypernode``
    """

    key: str
    value: str
    key_vid: str
    value_vid: str | None
    lexical: bool = False


@dataclass(frozen=True)
class LexicalCandidate:
    """A lexical hypernode found through spelling search.

    Attributes:
        node: hypernode.
        similarity: ``pg_trgm``'s ``word_similarity(query, node.value)``, from 0 to 1. How well the query matches the most similar part of the value.
    """

    node: Hypernode
    similarity: float


@dataclass(frozen=True)
class FactRow:
    """Fact to store.

    Attributes:
        record_id: record the fact was built from.
        anchor_id: id of anchor record fact is about, or ``None``.
        lane: see ``Lane``.
        text: actual text of this fact the LLM sees.
        sort_key: content hash: the set cover's last tie-break, identical in every store.
        nodes: fact's pairs in order.
    """

    record_id: str
    anchor_id: str | None
    lane: Lane
    text: str
    sort_key: str
    nodes: tuple[HypernodeSpec, ...]


@dataclass(frozen=True)
class Membership:
    """Link between a hypernode and a fact it belongs to.

    Attributes:
        fact_id: fact id.
        record_id: id of record the fact was built from.
        anchor_id: id of anchor record the fact is about, or ``None``.
    """

    fact_id: int
    record_id: str
    anchor_id: str | None


@dataclass(frozen=True)
class FactMeta:
    """Metadata about a canidate fact for the set cover.

    Attributes:
        id: fact id.
        anchor_id: id of anchor record fact is about, or ``None``.
        pair_count: fact's number of pairs (ties go to the larger fact).
        sort_key: content hash (the last tie-break).
        node_ids: ids of the fact's hypernodes among the ones asked about.
    """

    id: int
    anchor_id: str | None
    pair_count: int
    sort_key: str
    node_ids: frozenset[int]


@dataclass(frozen=True)
class FactView:
    """Retrieved fact.

    Attributes:
        id: fact id.
        record_id: record the fact was built from.
        anchor_id: id of anchor record fact is about, or ``None``.
        pairs: fact's ``"key": value`` pairs, in order.
        text: actual text of this fact the LLM sees.
    """

    id: int
    record_id: str
    anchor_id: str | None
    pairs: tuple[tuple[str, str], ...]
    text: str


class GraphStore(Protocol):
    """Stores the hypergraph: facts, shared hypernodes and memberships.

    Hypergraph data is generated data, rebuilt from the records. Core system does selection and set cover, store only reads and writes rows.

    Contract:
        - ``replace_facts`` runs in ``tx`` when given, but never commits it.
        - hypernodes are shared: write reuses an existing (key, value) pair, also when another transaction
          created it concurrently. Ids are stable while hypernode exists.
        - unused hypernodes are removed only by ``prune_nodes``.
    """

    @abstractmethod
    async def replace_facts(
        self,
        record_ids: Sequence[str],
        facts: Sequence[FactRow],
        tx: Tx | None = None,
        numbers: Sequence[NumberRow] = (),
    ) -> None:
        """Replaces all facts and numbers of ``record_ids``.

        Args:
            record_ids: records whose facts are dropped (re-indexed or deleted ones).
            facts: new fact rows, each row's ``record_id`` is in ``record_ids``.
            tx: transaction, or ``None``.
            numbers: records' numbers, used for filters.
        """
        ...

    @abstractmethod
    async def lock_records(
        self,
        record_ids: Sequence[str],
        tx: Tx | None = None,
        shared_ids: Sequence[str] = (),
    ) -> None:
        """Locks records for writing and for reading until ``tx`` finishes.

        ``record_ids`` are locked exclusively (write, delete), ``shared_ids`` for read (parents whose names the write copies).

        Writes that collide (e.g. machine renamed while one items are edited) run after each other. Later one sees prior one's commit.
        Take shared locks first, then exclusive ones, each in sorted order. Link targets are locked before the records that link to them.
        Otherwise writers can deadlock. A transaction may lock the same record again.
        If ``tx`` is ``None`` there is nothing to hold => return at once.
        """
        ...

    @abstractmethod
    def acquire_maintenance(self) -> AbstractAsyncContextManager[bool]:
        """Returns a context manager that yields ``True`` if this process may run maintenance now.
        ``False`` if another one does, in that case return and don't wait."""
        ...

    @abstractmethod
    async def get_nodes_for_values(
        self, lane: Lane, value_vids: Sequence[str]
    ) -> list[Hypernode]:
        """Returns hypernodes with one of given value vectors that belong to a fact of ``lane``."""
        ...

    @abstractmethod
    async def get_lexical_candidates(
        self, lane: Lane, query: str, min_similarity: float, limit: int
    ) -> list[LexicalCandidate]:
        """Returns lexical hypernodes of ``lane`` whose value is spelled like a part of ``query``.

        Similarity is ``pg_trgm``'s ``word_similarity(query, value)``. Postgres store finds candidates with the
        ``<%`` operator and the trigram index, setting ``pg_trgm.word_similarity_threshold`` to ``min_similarity``.

        Args:
            lane: ``fact`` or ``guideline``.
            query: query text for lexical search.
            min_similarity: candidates must have >= this similarity (``SearchSettings.lexical_min_similarity``).
            limit: return at most this many candidates.

        Returns:
            Candidates, most similar first.
        """
        ...

    @abstractmethod
    async def get_matching_anchor_ids(self, filters: Sequence[Filter]) -> set[str]:
        """Returns ids of anchor records that have a number that passes each one of ``filters``."""
        ...

    @abstractmethod
    async def get_memberships(
        self, lane: Lane, node_ids: Sequence[int], hub_limit: int | None
    ) -> dict[int, list[Membership]]:
        """Returns facts of ``lane`` each hypernode belongs to.

        Args:
            lane: ``fact`` or ``guideline``.
            node_ids: hypernodes.
            hub_limit: return at most ``hub_limit + 1`` facts per hypernode. If ``hub_limit + 1`` items were returned, the hypernode is a hub. ``None``: return all.

        Returns:
            Hypernode id -> its facts. Hypernodes without a fact in given ``lane`` are left out.
        """
        ...

    @abstractmethod
    async def get_fact_meta(
        self, fact_ids: Sequence[int], node_ids: Collection[int]
    ) -> list[FactMeta]:
        """Returns metadata of ``fact_ids`` for set cover: anchor id, pair count, sort key, and which of ``node_ids`` each contains."""
        ...

    @abstractmethod
    async def get_facts(self, fact_ids: Sequence[int]) -> list[FactView]:
        """Returns facts with their pairs and text in any order. Unknown ids should be left out."""
        ...

    @abstractmethod
    async def get_used_nodes(
        self, lane: Lane, after_id: int = 0, limit: int | None = None
    ) -> list[Hypernode]:
        """Returns hypernodes that belong to a fact of ``lane``. Paging mechanism.

        Args:
            lane: ``fact`` or ``guideline``.
            after_id: hypernode id, return only ones with greater id.
            limit: at most this many, ordered by id. ``None``: return all.
        """
        ...

    @abstractmethod
    async def prune_nodes(self) -> int:
        """Deletes floating hypernodes no fact uses. Returns deleted count."""
        ...
