"""What the ontology tells clients about its classes and properties (``Ontology.describe``)."""

from dataclasses import dataclass

from services.ograg.ontology.property import EdgeType
from services.search import SearchMode


@dataclass(frozen=True)
class ClassLabel:
    """Texts of a class shown to users.

    Attributes:
        display_name: name shown to users.
        comment: description shown to users.
    """

    display_name: str = ""
    comment: str = ""


@dataclass(frozen=True)
class PropertyDescription:
    """A property as clients see it.

    Attributes:
        range: local name of the range, e.g. ``Text`` or ``Machine``.
        display_name: name shown to users.
        comment: description shown to users.
        enum: allowed values, empty if any value is allowed.
        link: range is a record class: the value is a record id.
        edge: kind of link (``parent`` or ``simple``), ``None`` if the property is no link.
        delete_with_parent: deleting the parent deletes the record too.
        nested: range is a class that is not a record class: the value is a nested node.
        identity: values name the record.
        search: how the values are searched.
    """

    range: str
    display_name: str
    comment: str
    enum: tuple[str, ...]
    link: bool
    edge: EdgeType | None
    delete_with_parent: bool
    nested: bool
    identity: bool
    search: tuple[SearchMode, ...]


@dataclass(frozen=True)
class ClassDescription:
    """A class as clients see it.

    Attributes:
        display_name: name shown to users.
        comment: description shown to users.
        record: stored as records.
        anchor: the class search results are grouped by.
        file: records carry an uploaded file.
        guideline: records take the guideline lane: checked after the answer, not answered from.
        extractable: the document import extracts records of this class.
        properties: property name -> property, in ontology file order.
    """

    display_name: str
    comment: str
    record: bool
    anchor: bool
    file: bool
    guideline: bool
    extractable: bool
    properties: dict[str, PropertyDescription]
