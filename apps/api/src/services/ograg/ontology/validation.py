from __future__ import annotations

import math
from collections.abc import Generator, Mapping
from typing import TYPE_CHECKING

from services import Json, JsonObject
from services.ograg.ontology.names import (
    JSONLD_ID,
    JSONLD_TYPE,
    KEYWORD_PREFIX,
    NUMBER_RANGES,
    get_link_target_id,
    get_local_name,
    get_type,
    to_list,
)
from services.ograg.ontology.property import Property

if TYPE_CHECKING:  # at runtime it would be circular: model imports this module
    from services.ograg.ontology.model import Ontology

DROPPED_VALUE_SHOWN_LENGTH: int = 60

ERROR_NOT_ALLOWED: str = "not one of {allowed}"
ERROR_NOT_A_NUMBER: str = "not a number"
WARNING_DROPPED_NODE: str = "dropped node of type {node_type!r}"
WARNING_DROPPED_PROPERTY: str = "dropped unknown property {node_type}.{key}"
WARNING_DROPPED_LINK: str = "dropped link of {domain}.{name} without an id"
WARNING_DROPPED_NON_OBJECT: str = "dropped non-object value of {domain}.{name}"
WARNING_DROPPED_STRUCTURED: str = "dropped structured value of {domain}.{name}"
WARNING_DROPPED_VALUE: str = "dropped {domain}.{name} {shown!r}: {reason}"


def validate_node(
    ontology: Ontology, node: Mapping[str, Json], expected_type: str | None = None
) -> tuple[JsonObject, list[str]]:
    """Returns cleaned ``node`` validated on ``ontology``, and warnings about drops."""
    return _NodeValidator(ontology).validate(node, expected_type)


def parse_number(text: str) -> int | float | None:
    """Returns ``text`` as a number. ``int`` if no point present, else ``float``. ``None`` if ``text`` is NaN."""
    try:
        return int(text)
    except ValueError:
        pass
    try:
        number: float = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _get_number(text: str) -> int | float:
    """Returns value of a number property and parses it.

    Raises:
        ValueError: ``text`` is NaN.
    """
    number: int | float | None = parse_number(text)
    if number is None:
        raise ValueError(ERROR_NOT_A_NUMBER)
    return number


def _get_allowed_value(text: str, prop: Property) -> str:
    """Returns value to be stored. ``text``, or the ontology's spelling of an allowed value.

    Raises:
        ValueError: ``prop`` has allowed values and ``text`` is none of them.
    """
    if not prop.allowed:
        return text

    match: str | None = {val.casefold(): val for val in prop.allowed}.get(
        text.strip().casefold()
    )
    if match is None:
        raise ValueError(ERROR_NOT_ALLOWED.format(allowed=", ".join(prop.allowed)))
    return match


class _NodeValidator:
    """Validates a node and its nested nodes against an ``ontology``."""

    def __init__(self, ontology: Ontology):
        self.ontology: Ontology = ontology

    def validate(
        self, node: Mapping[str, Json], expected_type: str | None
    ) -> tuple[JsonObject, list[str]]:
        """Returns ``(cleaned node, drops)`` pair."""
        node_type: str = get_type(node, expected_type or "")
        if node_type not in self.ontology.classes or (
            expected_type and node_type != expected_type
        ):
            return {}, [WARNING_DROPPED_NODE.format(node_type=node_type)]

        clean: JsonObject = {JSONLD_TYPE: node_type}
        if JSONLD_ID in node:
            clean[JSONLD_ID] = str(node[JSONLD_ID])

        drops: list[str] = []
        for key, value in node.items():
            if key.startswith(KEYWORD_PREFIX):
                continue

            prop: Property | None = self.ontology.properties.get(
                (node_type, get_local_name(key))
            )
            if prop is None:
                drops.append(
                    WARNING_DROPPED_PROPERTY.format(node_type=node_type, key=key)
                )
                continue

            kept: list[Json] = self._get_kept_values(to_list(value), prop, drops)
            if kept:
                clean[prop.name] = kept if isinstance(value, list) else kept[0]

        return clean, drops

    def _get_kept_values(
        self, values: list[Json], prop: Property, warnings: list[str]
    ) -> list[Json]:
        """Returns ``values`` of ``prop`` that fit the ontology, adds to ``warnings`` for each drop."""
        kept: Generator[str | int | float | JsonObject | None] = (
            self._get_kept_value(val, prop, warnings) for val in values
        )
        return [val for val in kept if val is not None]

    def _get_kept_value(
        self, value: Json, prop: Property, warnings: list[str]
    ) -> str | int | float | JsonObject | None:
        """Returns ``value`` as kept, or ``None`` when it is dropped, adds to ``warnings`` if dropped."""
        if self.ontology.is_link(prop):
            return self._get_link_value(value, prop, warnings)
        if self.ontology.is_nested(prop):
            return self._get_nested_value(value, prop, warnings)
        return self._get_literal_value(value, prop, warnings)

    @staticmethod
    def _get_link_value(value: Json, prop: Property, warnings: list[str]) -> str | None:
        target_id: Json = get_link_target_id(value)
        if isinstance(target_id, (dict, list)) or target_id is None or target_id == "":
            warnings.append(
                WARNING_DROPPED_LINK.format(domain=prop.domain, name=prop.name)
            )
            return None
        return str(target_id)

    def _get_nested_value(
        self, value: Json, prop: Property, warnings: list[str]
    ) -> JsonObject | None:
        if not isinstance(value, dict):
            warnings.append(
                WARNING_DROPPED_NON_OBJECT.format(domain=prop.domain, name=prop.name)
            )
            return None
        child, child_warnings = self.validate(
            {JSONLD_TYPE: prop.range, **value}, prop.range
        )
        warnings += child_warnings
        has_properties: bool = len(child) > 1  # more than its @type
        return child if has_properties else None

    @staticmethod
    def _get_literal_value(
        value: Json, prop: Property, warnings: list[str]
    ) -> str | int | float | None:
        """Returns ``value`` as number for number properties, else text. ``None`` if dropped."""
        if isinstance(value, (dict, list)):
            warnings.append(
                WARNING_DROPPED_STRUCTURED.format(domain=prop.domain, name=prop.name)
            )
            return None
        if value is None or value == "":
            return None

        try:
            text: str = _get_allowed_value(str(value), prop)
            return _get_number(text) if prop.range in NUMBER_RANGES else text
        except ValueError as exc:
            shown = str(value)[:DROPPED_VALUE_SHOWN_LENGTH]
            warnings.append(
                WARNING_DROPPED_VALUE.format(
                    domain=prop.domain, name=prop.name, shown=shown, reason=exc
                )
            )
            return None
