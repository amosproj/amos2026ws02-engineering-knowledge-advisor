from enum import StrEnum


class TableName(StrEnum):
    RECORDS = "ograg_records"
    LINKS = "ograg_links"
    VECTORS = "ograg_vectors"
    DOCUMENTS = "ograg_documents"
    DOCUMENT_RECORDS = "ograg_document_records"
    HYPERNODES = "ograg_hypernodes"
    FACTS = "ograg_facts"
    FACT_NODES = "ograg_fact_nodes"
    NUMBERS = "ograg_numbers"


class CommonColumn(StrEnum):
    ID = "id"
    RECORD_ID = "record_id"
    NODE_ID = "node_id"
    ANCHOR_ID = "anchor_id"
    LANE = "lane"
    TEXT = "text"
    VALUE = "value"


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


class VectorColumn(StrEnum):
    KIND = "kind"
    EMBEDDING = "embedding"


class DocumentColumn(StrEnum):
    URI = "uri"
    MEDIA_TYPE = "media_type"
    SHA256 = "sha256"
    NAME = "name"
    STATUS = "status"
    ERROR = "error"
    NOTES = "notes"
    EXTRACTOR = "extractor"
    PROPERTIES = "properties"
    META = "meta"
    AUTHOR = "author"
    CREATED_AT = "created_at"


class DocumentRecordColumn(StrEnum):
    DOCUMENT_ID = "document_id"


class HypernodeColumn(StrEnum):
    KV_HASH = "kv_hash"
    KEY = "key"
    KEY_VID = "key_vid"
    VALUE_VID = "value_vid"
    LEXICAL = "lexical"


class FactColumn(StrEnum):
    PAIR_COUNT = "pair_count"
    SORT_KEY = "sort_key"
    PAIRS = "pairs"


class FactNodeColumn(StrEnum):
    FACT_ID = "fact_id"


class NumberColumn(StrEnum):
    PATH = "path"
