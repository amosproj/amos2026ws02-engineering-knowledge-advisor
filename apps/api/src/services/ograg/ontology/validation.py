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
ERROR_INVALID_VALUE: str = "{name} {shown!r} is invalid: {reason}"
ERROR_NOT_SINGLE_VALUE: str = "not a single value"
ERROR_BELOW_MIN_VALUE: str = "{name} must be at least {min_value}, found {found}"
ERROR_ABOVE_UPPER_BOUND: str = (
    "{name} must not be greater than {other}, found {found} and {other_found}"
)
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


def find_rule_violation(
    ontology: Ontology, node: Mapping[str, Json], submitted: Mapping[str, Json]
) -> str | None:
    """Returns why a value breaks a rule of its property, ``None`` if none does. Nested nodes are checked too.

    Rules: ``og:rejectInvalid``, ``og:minValue`` and ``og:upperBound``. Unlike a drop, a broken rule rejects the record.

    Args:
        ontology: the ontology holding the rules.
        node: ``submitted`` cleaned by ``validate_node``, so numbers are already parsed.
        submitted: the node as submitted: it still holds the invalid values the cleaning dropped.
    """
    return _find_rejected_value(ontology, get_type(node), submitted) or (
        _find_broken_number_rule(ontology, node)
    )


def _find_rejected_value(
    ontology: Ontology, node_type: str, submitted: Mapping[str, Json]
) -> str | None:
    """Returns why a submitted value of a property with ``og:rejectInvalid`` is invalid, ``None`` if all are valid."""
    for key, value in submitted.items():
        prop: Property | None = ontology.properties.get(
            (node_type, get_local_name(key))
        )
        if prop is None:  # @-keys and unknown properties
            continue
        for val in to_list(value):
            if ontology.is_nested(prop) and isinstance(val, dict):
                nested: str | None = _find_rejected_value(ontology, prop.range, val)
                if nested is not None:
                    return nested
            elif prop.reject_invalid and val is not None and val != "":
                reason: str | None = _get_invalid_reason(val, prop)
                if reason is not None:
                    shown = str(val)[:DROPPED_VALUE_SHOWN_LENGTH]
                    return ERROR_INVALID_VALUE.format(
                        name=prop.name, shown=shown, reason=reason
                    )
    return None


def _get_invalid_reason(value: Json, prop: Property) -> str | None:
    """Returns why the cleaning would drop the literal ``value`` of ``prop``, ``None`` if it would keep it."""
    if isinstance(value, (dict, list)):
        return ERROR_NOT_SINGLE_VALUE
    try:
        _parse_literal(value, prop)
    except ValueError as exc:
        return str(exc)
    return None


def _find_broken_number_rule(
    ontology: Ontology, node: Mapping[str, Json]
) -> str | None:
    """Returns why a number of the cleaned ``node`` breaks ``og:minValue`` or ``og:upperBound``, ``None`` if none does."""
    node_type: str = get_type(node)
    for name, value in node.items():
        prop: Property | None = ontology.properties.get((node_type, name))
        if prop is None:  # @type and @id
            continue
        if ontology.is_nested(prop):
            for child in to_list(value):
                violation: str | None = (
                    _find_broken_number_rule(ontology, child)
                    if isinstance(child, dict)
                    else None
                )
                if violation is not None:
                    return violation
            continue

        numbers: list[int | float] = _get_numbers(value)
        if not numbers:
            continue
        if prop.min_value is not None and min(numbers) < prop.min_value:
            return ERROR_BELOW_MIN_VALUE.format(
                name=name, min_value=prop.min_value, found=min(numbers)
            )
        bound_name: str | None = prop.upper_bound
        bounds: list[int | float] = (
            _get_numbers(node[bound_name])
            if bound_name is not None and bound_name in node
            else []
        )
        if bounds and max(numbers) > min(bounds):
            return ERROR_ABOVE_UPPER_BOUND.format(
                name=name,
                other=bound_name,
                found=max(numbers),
                other_found=min(bounds),
            )
    return None


def _get_numbers(value: Json) -> list[int | float]:
    """Returns the numbers among ``value``, one value or a list."""
    return [
        val
        for val in to_list(value)
        if isinstance(val, (int, float)) and not isinstance(val, bool)
    ]


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


def _parse_literal(value: Json, prop: Property) -> str | int | float:
    """Returns ``value`` as number for number properties, else as text, in the ontology's spelling of allowed values.

    Raises:
        ValueError: ``value`` is not allowed, or not a number for a number property.
    """
    text: str = _get_allowed_value(str(value), prop)
    return _get_number(text) if prop.range in NUMBER_RANGES else text


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
            return _parse_literal(value, prop)
        except ValueError as exc:
            shown = str(value)[:DROPPED_VALUE_SHOWN_LENGTH]
            warnings.append(
                WARNING_DROPPED_VALUE.format(
                    domain=prop.domain, name=prop.name, shown=shown, reason=exc
                )
            )
            return None
