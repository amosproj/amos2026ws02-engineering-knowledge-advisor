from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from services import Json, JsonObject, Lane, Link
from services.ograg.ontology import validation
from services.ograg.ontology.names import (
    LITERAL_RANGES,
    get_type,
    to_list,
)
from services.ograg.ontology.parsing import (
    Declarations,
    get_version,
    parse_document,
    read_document,
)
from services.ograg.ontology.property import Property


def _matches_all(graph: Mapping[str, Json], conditions: dict[str, list[str]]) -> bool:
    """Whether every property in ``conditions`` has allowed values in ``graph``.
    ``False`` if ``conditions`` contains a property that has a ``None`` value in ``graph``.
    """
    for prop_name, allowed in conditions.items():
        value: Json = graph.get(prop_name)
        values: list[Json] = [] if value is None else to_list(value)
        if not values or not all(_is_allowed(val, allowed) for val in values):
            return False
    return True


def _is_allowed(value: Json, allowed: list[str]) -> bool:
    """Whether a ``value`` is in ``allowed``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value in allowed
    return any(validation.parse_number(text) == value for text in allowed)


@dataclass
class Ontology:
    """Classes and properties records may use.

    Attributes:
        classes: class names.
        properties: (domain class, property name) -> property
        anchor_class: the class marked ``"og:anchor": true`` facts belong to.
        version: content hash of ontology, records store version they were validated with.
        record_classes: classes marked ``"og:record": true``.
        extractable_classes: record classes marked ``"og:extractable": true``, document import extracts only these (none marked => nothing extracted).
        guideline_when: conditions when class counts as a guideline (class -> property -> values).
    """

    classes: set[str]
    properties: dict[tuple[str, str], Property]
    anchor_class: str
    version: str = ""
    record_classes: list[str] = field(default_factory=list)
    extractable_classes: list[str] = field(default_factory=list)
    guideline_when: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> Ontology:
        """Loads an ontology JSON-LD file.

        Raises:
            OSError: file cannot be read.
            json.JSONDecodeError: file is not JSON.
            OntologyError: file holds no JSON object, or ontology is malformed.
        """
        return cls.from_jsonld(read_document(path))

    @classmethod
    def from_jsonld(cls, document: Mapping[str, Json]) -> Ontology:
        """Builds ontology from ``document``, a parsed JSON-LD document.

        Raises:
            OntologyError: ontology is malformed:
                - ``@graph`` is not a list of objects, or an annotation's value has a wrong type
                - not exactly one class marked as anchor
                - anchor or extractable class is not a record
                - property has unknown domain, range or search mode
                - ``og:parentLink`` is not on a property marked as a link
                - ``og:parentLink`` lead back to their own class
                - ``og:guidelineWhen`` is not on a record class or names a property its class doesn't have.
        """
        declared: Declarations = parse_document(document)
        return cls(
            classes=declared.classes,
            properties=declared.properties,
            anchor_class=declared.anchor_classes[0],
            version=get_version(document),
            record_classes=declared.record_classes,
            extractable_classes=declared.extractable_classes,
            guideline_when=declared.guideline_when,
        )

    def is_link(self, prop: Property) -> bool:
        """Whether ``prop``'s range is set to a record class."""
        return prop.range in self.record_classes

    def is_nested(self, prop: Property) -> bool:
        """Whether ``prop`` is a nested class."""
        return prop.range in self.classes and not self.is_link(prop)

    def get_identity_property_names(self) -> dict[str, list[str]]:
        """Returns map of record class -> names of its identity properties."""
        return {
            cls: [prop.name for prop in self._get_properties_of(cls) if prop.identity]
            for cls in self.record_classes
        }

    def get_link_names(self, cls: str) -> set[str]:
        """Returns names of ``cls``'s link properties."""
        return {
            prop.name for prop in self._get_properties_of(cls) if self.is_link(prop)
        }

    def get_links(self, graph: Mapping[str, Json]) -> list[Link]:
        """Returns one ``Link`` per target id of a validated record.

        Args:
            graph: record's graph.
        """
        cls: str = get_type(graph)
        found: list[Link] = []
        for key, value in graph.items():
            prop = self.properties.get((cls, key))
            if prop is not None and self.is_link(prop):
                found += [
                    Link(prop.name, str(target_id)) for target_id in to_list(value)
                ]
        return found

    def get_lane(self, graph: Mapping[str, Json]) -> Lane:
        """Returns the lane for the given record's facts. ``guideline`` when record's values all match its class's ``og:guidelineWhen``, else ``fact``.

        Args:
            graph: validated record graph.
        """
        cls: str = get_type(graph)
        conditions: dict[str, list[str]] | None = self.guideline_when.get(cls)
        if conditions and _matches_all(graph, conditions):
            return Lane.GUIDELINE
        return Lane.FACT

    def copy_with_changes(
        self, add: Iterable[Property] = (), drop: Iterable[tuple[str, str]] = ()
    ) -> Ontology:
        """Returns copy of current ontology. Adds properties (and their classes) and drops ``(class, property)`` pairs from copy."""
        add, drop = list(add), set(drop)
        properties: dict[tuple[str, str], Property] = {
            k: prop for k, prop in self.properties.items() if k not in drop
        }
        properties.update({(prop.domain, prop.name): prop for prop in add})
        classes: set[str] = self.classes | {
            cls
            for prop in add
            for cls in (prop.domain, prop.range)
            if cls not in LITERAL_RANGES
        }
        return replace(self, classes=classes, properties=properties)

    def get_properties_under(self, cls: str) -> set[tuple[str, str]]:
        """Returns every (class, property) pair a node of class ``cls`` can hold, including nested nodes."""
        found: set[tuple[str, str]] = set()

        cls_queue: list[str] = [cls]
        processed_classes: set[str] = set()
        while cls_queue:
            current_cls: str = cls_queue.pop()
            if current_cls in processed_classes:
                continue

            processed_classes.add(current_cls)
            for prop in self._get_properties_of(current_cls):
                found.add((prop.domain, prop.name))
                if self.is_nested(prop):
                    cls_queue.append(prop.range)

        return found

    def get_record_properties(self) -> set[tuple[str, str]]:
        """Returns every (class, property) pair a record can hold."""
        return set().union(
            *(self.get_properties_under(cls) for cls in self.record_classes)
        )

    def validate_node(
        self, node: Mapping[str, Json], expected_type: str | None = None
    ) -> tuple[JsonObject, list[str]]:
        """Returns cleaned ``node`` validated on the ontology, and warnings about what was dropped.

        Link values may be an id, ``{"@id": id}`` or a list of any of these. Clean node will hold plain ids.

        This method does **NOT** check:
        - whether targets actually exist
        - whether text can be stored

        Args:
            node: JSON-LD node, nested nodes get their class from the property's range.
            expected_type: class ``node`` must be, or ``None`` meaning its own ``@type``.

        Returns:
            pair: (clean node, drop warnings)
        """
        return validation.validate_node(self, node, expected_type)

    def _get_properties_of(self, cls: str) -> list[Property]:
        return [prop for (domain, _), prop in self.properties.items() if domain == cls]
