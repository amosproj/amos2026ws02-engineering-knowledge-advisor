from enum import StrEnum


class TableName(StrEnum):
    RECORDS = "ograg_records"
    LINKS = "ograg_links"


class CommonColumn(StrEnum):
    ID = "id"
    RECORD_ID = "record_id"


class RecordColumn(StrEnum):
    CLS = "cls"
    GRAPH = "graph"
    INPUT = "input"
    ONTOLOGY_VERSION = "ontology_version"
    REVIEW = "review"
    UPDATED_AT = "updated_at"
    IDENTITY_VALUES = "identity_values"


class LinkColumn(StrEnum):
    POSITION = "position"
    PROPERTY_NAME = "property_name"
    TARGET_ID = "target_id"
