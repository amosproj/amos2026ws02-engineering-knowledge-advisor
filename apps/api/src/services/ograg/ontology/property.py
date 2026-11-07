from dataclasses import dataclass
from enum import StrEnum

from services.ograg.ontology.names import LITERAL_RANGES, NUMBER_RANGES
from services.search import SearchMode


class EdgeType(StrEnum):
    """Kind of link (``og:edgeType``)."""

    PARENT = "parent"
    """Link to the record's parent. Losing last one marks the record for review."""
    SIMPLE = "simple"
    """Default link."""


@dataclass(frozen=True)
class Property:
    """A property inside the ontology.

    Attributes:
        name: property name.
        domain: class the property resides in.
        range: class (nested node, or link), or literal type.
        identity: whether values of this property name the record and are copied into the facts of records whose parent links point to it.
        edge: kind of link set by ``og:edgeType``, ``None`` if not set (a link is then ``simple``).
        search: ``None`` is parsed by range: ``FILTER`` for numbers, ``SEMANTIC`` for other literals, none for class ranges.
        provenance: source document's id.
        allowed: allowed property values.
        delete_with_parent: parent link whose target's deletion deletes the record too.
        display_name: name shown to users.
        comment: description shown to users.
    """

    name: str
    domain: str
    range: str
    identity: bool = False
    edge: EdgeType | None = None
    search: tuple[SearchMode, ...] | None = None
    provenance: bool = False
    allowed: tuple[str, ...] = ()
    delete_with_parent: bool = False
    display_name: str = ""
    comment: str = ""

    @property
    def is_parent_link(self) -> bool:
        """Link to the record's parent, losing last one marks the record for review."""
        return self.edge is EdgeType.PARENT

    def __post_init__(self) -> None:
        """Sets the default search modes by range when none are given."""
        if self.search is None:
            object.__setattr__(self, "search", self._get_default_search_modes())

    def _get_default_search_modes(self) -> tuple[SearchMode, ...]:
        if self.range in NUMBER_RANGES:
            return (SearchMode.FILTER,)
        if self.range in LITERAL_RANGES:
            return (SearchMode.SEMANTIC,)
        return ()
