"""
Class annotations:
- ``og:record``: stored as records
- ``og:anchor``: only one class holds this annotation, this is the grouping key for search results
- ``og:extractable``: whether the document import extracts records of this class (none marked => none extracted)
- ``og:guidelineWhen``: record takes the guideline lane when all ``{property: [values]}`` match

Property annotations:
- ``og:identity``: copied as context into facts of records that link to it
- ``og:parentLink``: link to the record's parent, losing last one leaves the record for review
- ``og:search``: ``semantic``, ``lexical`` or ``filter``: text default is ``semantic``, numbers work only with ``filter``
- ``og:author``: filled by uploader
- ``og:provenance``: filled with source document id of a record

A property whose range is a record class is a *link*. Records then store the target id.
"""

from __future__ import annotations

from collections.abc import Mapping

from services import Json

NUMBER_RANGES: set[str] = {"Number"}
LITERAL_RANGES: set[str] = {"Text", "URL", "Date"} | NUMBER_RANGES

# JSON-LD keys of a node and kinds of graph items
KEYWORD_PREFIX: str = "@"
JSONLD_TYPE: str = "@type"
JSONLD_ID: str = "@id"
JSONLD_GRAPH: str = "@graph"
CLASS: str = "Class"
PROPERTY: str = "Property"
# keys of a property definition (``@context`` in ontology)
DOMAIN: str = "domain"
RANGE: str = "range"

# class annotations
OG_RECORD: str = "og:record"
OG_ANCHOR: str = "og:anchor"
OG_EXTRACTABLE: str = "og:extractable"
OG_GUIDELINE_WHEN: str = "og:guidelineWhen"
CLASS_FLAGS: tuple[str, ...] = (OG_ANCHOR, OG_RECORD, OG_EXTRACTABLE)

# property annotations
OG_IDENTITY: str = "og:identity"
OG_PARENT_LINK: str = "og:parentLink"
OG_SEARCH: str = "og:search"
OG_AUTHOR: str = "og:author"
OG_PROVENANCE: str = "og:provenance"
OG_ALLOWED_VALUES: str = "og:allowedValues"
ENUM: str = "enum"  # short name for og:allowedValues


def get_local_name(iri: str) -> str:
    """Normalize a name, e.g. ``og:hasConstraint``, ``https://...#hasConstraint`` to ``hasConstraint``."""
    for sep in ("#", "/", ":"):
        if sep in iri:
            iri = iri.rsplit(sep, maxsplit=1)[1]
    return iri


def get_link_target_id(value: Json) -> Json:
    """Returns target id a link ``value`` holds: ``value["@id"]`` if ``value`` is a dict, else ``value``."""
    return value.get(JSONLD_ID) if isinstance(value, dict) else value


def to_list[T](value: T | list[T]) -> list[T]:
    """Returns list-wrapped ``value``, or ``value`` if already a list."""
    return value if isinstance(value, list) else [value]


def get_type(node: Mapping[str, Json], default: str = "") -> str:
    """Returns the type of ``node`` if set, otherwise ``default``."""
    return get_local_name(str(node.get(JSONLD_TYPE, default)))
