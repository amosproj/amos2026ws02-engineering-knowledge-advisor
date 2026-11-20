from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from services.database import Tx


class Lane(StrEnum):
    """The lane a record's facts take (``Ontology.get_lane``). Members are plain strings."""

    FACT = "fact"
    """Searched for as facts."""
    GUIDELINE = "guideline"
    """Checked against as guidelines."""


@dataclass(frozen=True)
class HypernodeSpec:
    """``key: value`` pairing of a fact without ids.

    Attributes:
        key: e.g. ``"AssemblyGroup name"``
        value: e.g. ``"Input tray"``
        key_vid: vector id of the key's embedding (kind ``key``).
        value_vid: vector id of the value's embedding (kind ``value``). ``None`` for no semantic search.
        lexical: whether spelling search applies to this pairing.
    """

    key: str
    value: str
    key_vid: UUID
    value_vid: UUID | None
    lexical: bool = False


@dataclass(frozen=True)
class FactRow:
    """Knowledge fact to store.

    Attributes:
        record_id: record fact was derived from.
        anchor_id: anchor record's id the fact is about, or ``None``.
        lane: see ``Lane`` class.
        text: what the LLM receives when this fact is used as context.
        sort_key: content hash for deterministic candidate fact selection, set cover's last tie-break when coverage and pair count are equal.
        nodes: fact's pairs in order.
    """

    record_id: str
    anchor_id: str | None
    lane: Lane
    text: str
    sort_key: str
    nodes: tuple[HypernodeSpec, ...]


@dataclass(frozen=True)
class FactView:
    """Retrieved knowledge fact.

    Attributes:
        id: fact id.
        record_id: record fact was derived from.
        anchor_id: anchor record's id the fact is about, or ``None``.
        pairs: fact's ``"key": value`` pairings in order.
        text: what the LLM receives when this fact is used as context.
    """

    id: int
    record_id: str
    anchor_id: str | None
    pairs: tuple[tuple[str, str], ...]
    text: str


class GraphStore(Protocol):
    """Stores the hypergraph's facts, shared hypernodes and memberships.

    This store only reads and writes rows. Writes reuse an existing (key, value) pair, also when another transaction created it concurrently.
    """

    @abstractmethod
    async def replace_facts(
        self,
        record_ids: Sequence[str],
        facts: Sequence[FactRow],
        tx: Tx | None = None,
    ) -> None:
        """Replaces all facts of ``record_ids``.

        Args:
            record_ids: records whose facts are to be dropped, first.
            facts: new fact rows to index, each ``FactRow.record_id`` is in ``record_ids``.
            tx: transaction, or ``None``.
        """
        ...

    @abstractmethod
    async def get_facts(self, fact_ids: Sequence[int]) -> list[FactView]:
        """Returns facts with their pairs and text in any order. Unknown ids are left out."""
        ...

    @abstractmethod
    async def prune_nodes(self) -> int:
        """Deletes floating hypernodes no fact references and returns delete count. Run inside its own transaction and never inside a write."""
        ...
