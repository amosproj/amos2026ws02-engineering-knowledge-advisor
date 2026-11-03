from dataclasses import dataclass

from services.ograg.ontology.names import LITERAL_RANGES, NUMBER_RANGES
from services.search import SearchMode


@dataclass(frozen=True)
class Property:
    """A property inside the ontology.

    Attributes:
        name: property name.
        domain: class the property resides in.
        range: class (nested node, or link), or literal type.
        identity: whether values of this property name the record and are copied into the facts of records whose parent links point to it.
        is_parent_link: link to the record's parent, losing last one marks the record for review.
        search: ``None`` is parsed by range: ``FILTER`` for numbers, ``SEMANTIC`` for other literals, none for class ranges.
        author: whether this property holds the author of the record.
        provenance: source document's id.
        allowed: allowed property values.
    """

    name: str
    domain: str
    range: str
    identity: bool = False
    is_parent_link: bool = False
    search: tuple[SearchMode, ...] | None = None
    author: bool = False
    provenance: bool = False
    allowed: tuple[str, ...] = ()

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
