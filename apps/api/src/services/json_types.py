"""Types for parsed JSON objects. Used for nodes and ontology items.
Parameters a function only reads take ``Mapping[str, Json]`` and not ``dict[str, Json]``.
"""

from typing import Annotated

from pydantic import Field

type Json = Annotated[
    str | int | float | bool | None | list[Json] | dict[str, Json],
    Field(description="Any JSON value."),
]
type JsonObject = Annotated[dict[str, Json], Field(description="JSON object.")]
