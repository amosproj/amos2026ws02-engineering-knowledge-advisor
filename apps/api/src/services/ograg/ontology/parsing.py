from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from services import Json, JsonObject, SearchMode
from services.ograg.ontology.names import (
    CLASS,
    CLASS_FLAGS,
    DOMAIN,
    ENUM,
    JSONLD_GRAPH,
    JSONLD_ID,
    JSONLD_TYPE,
    LITERAL_RANGES,
    OG_ALLOWED_VALUES,
    OG_ANCHOR,
    OG_AUTHOR,
    OG_EXTRACTABLE,
    OG_GUIDELINE_WHEN,
    OG_IDENTITY,
    OG_PARENT_LINK,
    OG_PROVENANCE,
    OG_RECORD,
    OG_SEARCH,
    PROPERTY,
    RANGE,
    get_local_name,
)
from services.ograg.ontology.property import Property

MODE_NAMES: set[str] = {mode.value for mode in SearchMode}
VERSION_LENGTH: int = 12

ERROR_UNKNOWN_SEARCH_MODES: str = (
    "property {domain}.{name} has unknown search modes {modes}"
)
ERROR_SEARCH_MODES_NOT_TEXTS: str = f"property {{domain}}.{{name}} needs a list of texts in {OG_SEARCH!r}, found {{found!r}}"
ERROR_ALLOWED_VALUES_NOT_LIST: str = f"property {{domain}}.{{name}} needs a list in {OG_ALLOWED_VALUES!r} or {ENUM!r}, found {{found!r}}"
ERROR_DOCUMENT_NOT_OBJECT: str = "ontology file must hold a JSON object"
ERROR_GRAPH_NOT_OBJECTS: str = f"ontology needs {JSONLD_GRAPH!r} as a list of objects"
ERROR_ANCHOR_COUNT: str = f'ontology must mark exactly one class with "{OG_ANCHOR}": true, found {{anchor_classes}}'
ERROR_ANCHOR_NOT_RECORD: str = (
    f'anchor class {{anchor_cls!r}} must be a record class ("{OG_RECORD}": true)'
)
ERROR_EXTRACTABLE_NOT_RECORD: str = (
    f'extractable classes must be record classes ("{OG_RECORD}": true): {{classes}}'
)
ERROR_ITEM_WITHOUT_KEY: str = "ontology item has no {key!r}: {item}"
ERROR_PROPERTY_WITHOUT_KEY: str = "property {name!r} has no {key!r}"
ERROR_UNKNOWN_DOMAIN: str = "property {name!r} has an unknown domain"
ERROR_UNKNOWN_RANGE: str = "property {name!r} has an unknown range"
ERROR_PARENT_LINK_NOT_LINK: str = (
    f"{OG_PARENT_LINK!r} on {{domain}}.{{name}}, which is not a link to a record class"
)
ERROR_PARENT_LINK_CYCLE: str = (
    f"{OG_PARENT_LINK!r} links between classes must not be cyclic: {{cycle_classes}}"
)
ERROR_GUIDELINE_WHEN_ON_RECORD: str = (
    f"{OG_GUIDELINE_WHEN!r} of {{cls!r}} must be on a record class"
)
ERROR_GUIDELINE_WHEN_UNKNOWN_PROPS: str = f"{OG_GUIDELINE_WHEN!r} of {{cls!r}} names properties the class does not have: {{prop_names}}"
ERROR_GUIDELINE_WHEN_NOT_OBJECT: str = f"{OG_GUIDELINE_WHEN!r} of {{cls!r}} must be an object of 'property -> list of values', found {{found!r}}"
ERROR_GUIDELINE_WHEN_NOT_TEXTS: str = f"{OG_GUIDELINE_WHEN!r} of {{cls!r}} needs a list of texts for {{prop_name!r}}, found {{found!r}}"


class OntologyError(ValueError):
    """Ontology is malformed and cannot be loaded."""


def read_document(path: str | Path) -> JsonObject:
    """Returns the parsed ontology file at ``path``.

    Raises:
        OSError: file cannot be read.
        json.JSONDecodeError: file is not JSON.
        OntologyError: file holds no JSON object.
    """
    document: Json = json.loads(Path(path).read_text("utf-8"))
    if not isinstance(document, dict):
        raise OntologyError(ERROR_DOCUMENT_NOT_OBJECT)
    return document


def parse_document(document: Mapping[str, Json]) -> Declarations:
    """Returns the checked declarations of ``document``, a parsed JSON-LD ontology.

    Raises:
        OntologyError: ontology is malformed (see ``Ontology.from_jsonld``).
    """
    declared = Declarations()
    for item in _get_graph_items(document):
        declared.read(item)
    declared.validate()
    return declared


def get_version(document: Mapping[str, Json]) -> str:
    """Returns content hash of ``document``. Equal documents have equal versions."""
    data: bytes = json.dumps(document, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()[:VERSION_LENGTH]


def _get_graph_items(document: Mapping[str, Json]) -> list[JsonObject]:
    """Returns items of ontology's ``@graph``.

    Raises:
        OntologyError: ``@graph`` is missing, or not a list of objects.
    """
    graph: Json = document.get(JSONLD_GRAPH)
    if not isinstance(graph, list):
        raise OntologyError(ERROR_GRAPH_NOT_OBJECTS)
    items: list[JsonObject] = [item for item in graph if isinstance(item, dict)]
    if len(items) != len(graph):
        raise OntologyError(ERROR_GRAPH_NOT_OBJECTS)
    return items


def _get_texts(value: Json) -> list[str] | None:
    """Returns ``value`` if it is a list of strings, else ``None``."""
    if not isinstance(value, list):
        return None
    strings: list[str] = [val for val in value if isinstance(val, str)]
    return strings if len(strings) == len(value) else None


def _get_required_name(item: Mapping[str, Json], key: str, missing: str) -> str:
    """Returns local name of ``item[key]``.

    Args:
        item: item of the ontology ``@graph``.
        key: ``item`` must have this key.
        missing: error if it doesn't.

    Raises:
        OntologyError: ``item`` has no ``key``.
    """
    if key not in item:
        raise OntologyError(missing)
    return get_local_name(str(item[key]))


def _find_parent_cycle(
    cls_path: list[str], parent_classes: Mapping[str, list[str]]
) -> list[str] | None:
    """Returns a path of parent classes from ``cls_path[-1]`` back to ``cls_path[0]``, or ``None`` if there are none.

    Args:
        cls_path: classes walked so far, starting at the class to check.
        parent_classes: class -> classes its parent links point to.
    """
    for parent_cls in parent_classes.get(cls_path[-1], []):
        if parent_cls == cls_path[0]:
            return [*cls_path, parent_cls]
        if parent_cls not in cls_path:
            cycle_classes: list[str] | None = _find_parent_cycle(
                [*cls_path, parent_cls], parent_classes
            )
            if cycle_classes is not None:
                return cycle_classes
    return None


@dataclass
class Declarations:
    """Helper to parse JSON-LD ontology."""

    classes: set[str] = field(default_factory=set)
    properties: dict[tuple[str, str], Property] = field(default_factory=dict)
    flags: dict[str, list[str]] = field(
        default_factory=lambda: {flag: [] for flag in CLASS_FLAGS}
    )
    guideline_when: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    @property
    def anchor_classes(self) -> list[str]:
        return self.flags[OG_ANCHOR]

    @property
    def record_classes(self) -> list[str]:
        return self.flags[OG_RECORD]

    @property
    def extractable_classes(self) -> list[str]:
        return self.flags[OG_EXTRACTABLE]

    def read(self, item: Mapping[str, Json]) -> None:
        """Parses ``item``, one class or property item of the ontology ``@graph``.

        Raises:
            OntologyError:
                - ``item`` has no ``@id`` or ``@type``
                - property has no ``domain`` or ``range``
                - unknown ``SearchMode``
                - or an annotation's value has a wrong type
        """
        missing: str = ERROR_ITEM_WITHOUT_KEY
        name: str = _get_required_name(
            item, JSONLD_ID, missing.format(key=JSONLD_ID, item=item)
        )
        kind: str = _get_required_name(
            item, JSONLD_TYPE, missing.format(key=JSONLD_TYPE, item=item)
        )
        if kind == CLASS:
            self._parse_class(name, item)
        elif kind == PROPERTY:
            self._parse_property(name, item)

    def _parse_class(self, name: str, item: Mapping[str, Json]) -> None:
        self.classes.add(name)
        for flag, flagged in self.flags.items():
            if item.get(flag) is True:
                flagged.append(name)
        if OG_GUIDELINE_WHEN in item:
            self.guideline_when[name] = self._parse_guideline_when(
                name, item[OG_GUIDELINE_WHEN]
            )

    def _parse_guideline_when(self, cls: str, conditions: Json) -> dict[str, list[str]]:
        if not isinstance(conditions, dict):
            raise OntologyError(
                ERROR_GUIDELINE_WHEN_NOT_OBJECT.format(cls=cls, found=conditions)
            )
        parsed: dict[str, list[str]] = {}
        for prop_name, values in conditions.items():
            texts: list[str] | None = _get_texts(values)
            if texts is None:
                raise OntologyError(
                    ERROR_GUIDELINE_WHEN_NOT_TEXTS.format(
                        cls=cls, prop_name=prop_name, found=values
                    )
                )
            parsed[prop_name] = texts
        return parsed

    def _parse_property(self, name: str, item: Mapping[str, Json]) -> None:
        missing: str = ERROR_PROPERTY_WITHOUT_KEY
        domain: str = _get_required_name(
            item, DOMAIN, missing.format(name=name, key=DOMAIN)
        )
        search: Json = item.get(OG_SEARCH)
        allowed: Json = item.get(ENUM) or item.get(OG_ALLOWED_VALUES) or []
        if not isinstance(allowed, list):
            raise OntologyError(
                ERROR_ALLOWED_VALUES_NOT_LIST.format(
                    domain=domain, name=name, found=allowed
                )
            )

        prop = Property(
            name=name,
            domain=domain,
            range=_get_required_name(item, RANGE, missing.format(name=name, key=RANGE)),
            identity=item.get(OG_IDENTITY) is True,
            is_parent_link=item.get(OG_PARENT_LINK) is True,
            search=None
            if search is None
            else self._parse_search_modes(domain, name, search),
            author=item.get(OG_AUTHOR) is True,
            provenance=item.get(OG_PROVENANCE) is True,
            allowed=tuple(map(str, allowed)),
        )
        self.properties[(prop.domain, prop.name)] = prop

    def _parse_search_modes(
        self, domain: str, name: str, modes: Json
    ) -> tuple[SearchMode, ...]:
        texts: list[str] | None = _get_texts(modes)
        if texts is None:
            raise OntologyError(
                ERROR_SEARCH_MODES_NOT_TEXTS.format(
                    domain=domain, name=name, found=modes
                )
            )
        unknown: set[str] = set(texts) - MODE_NAMES
        if unknown:
            raise OntologyError(
                ERROR_UNKNOWN_SEARCH_MODES.format(
                    domain=domain, name=name, modes=unknown
                )
            )
        return tuple(map(SearchMode, texts))

    def validate(self) -> None:
        """Raises ``OntologyError`` for invalid declarations."""
        self._validate_anchor()
        self._validate_extractable_classes()
        self._validate_properties()
        self._validate_parent_links()
        self._validate_guideline_when()

    def _validate_parent_links(self) -> None:
        """
        Raises:
            OntologyError: parent link leads back to its own class, which could produce deadlocks
        """
        parent_classes: dict[str, list[str]] = {}
        for prop in self.properties.values():
            if prop.is_parent_link:
                parent_classes.setdefault(prop.domain, []).append(prop.range)
        for cls in parent_classes:
            cycle_classes: list[str] | None = _find_parent_cycle([cls], parent_classes)
            if cycle_classes is not None:
                raise OntologyError(
                    ERROR_PARENT_LINK_CYCLE.format(
                        cycle_classes=" -> ".join(cycle_classes)
                    )
                )

    def _validate_anchor(self) -> None:
        # only one anchor class allowed
        if len(self.anchor_classes) != 1:
            raise OntologyError(
                ERROR_ANCHOR_COUNT.format(anchor_classes=self.anchor_classes)
            )

        # anchors must be records
        if self.anchor_classes[0] not in self.record_classes:
            raise OntologyError(
                ERROR_ANCHOR_NOT_RECORD.format(anchor_cls=self.anchor_classes[0])
            )

    def _validate_extractable_classes(self) -> None:
        # extractable classes must be records
        non_record_classes: list[str] = [
            cls for cls in self.extractable_classes if cls not in self.record_classes
        ]
        if non_record_classes:
            raise OntologyError(
                ERROR_EXTRACTABLE_NOT_RECORD.format(classes=non_record_classes)
            )

    def _validate_properties(self) -> None:
        for prop in self.properties.values():
            # domain has to be known class
            if prop.domain not in self.classes:
                raise OntologyError(ERROR_UNKNOWN_DOMAIN.format(name=prop.name))

            # literal ranges must be known
            if prop.range not in self.classes and prop.range not in LITERAL_RANGES:
                raise OntologyError(ERROR_UNKNOWN_RANGE.format(name=prop.name))

            # parent classes must be records
            if prop.is_parent_link and prop.range not in self.record_classes:
                raise OntologyError(
                    ERROR_PARENT_LINK_NOT_LINK.format(
                        domain=prop.domain, name=prop.name
                    )
                )

    def _validate_guideline_when(self) -> None:
        for cls, conditions in self.guideline_when.items():
            # class of condition must be a record
            if cls not in self.record_classes:
                raise OntologyError(ERROR_GUIDELINE_WHEN_ON_RECORD.format(cls=cls))

            # conditions may only name properties of the class
            unknown_prop_names: list[str] = [
                prop_name
                for prop_name in conditions
                if (cls, prop_name) not in self.properties
            ]
            if unknown_prop_names:
                raise OntologyError(
                    ERROR_GUIDELINE_WHEN_UNKNOWN_PROPS.format(
                        cls=cls, prop_names=unknown_prop_names
                    )
                )
