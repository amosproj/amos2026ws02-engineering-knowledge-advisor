"""Types for parsed JSON objects. Used for nodes and ontology items.
Parameters a function only reads take ``Mapping[str, Json]`` and not ``dict[str, Json]``.
"""

type Json = str | int | float | bool | None | list[Json] | dict[str, Json]
type JsonObject = dict[str, Json]
