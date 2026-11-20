"""Types for parsed JSON objects. Used for nodes and ontology items.
Parameters a function only reads take ``Mapping[str, JsonValue]`` and not ``dict[str, JsonValue]``.
"""

from typing import Annotated

from pydantic import Field

type JsonValue = Annotated[
    str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue],
    Field(description="Any JSON value."),
]
type JsonObject = Annotated[dict[str, JsonValue], Field(description="JSON object.")]
