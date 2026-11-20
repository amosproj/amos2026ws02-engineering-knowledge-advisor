from enum import StrEnum


class TableName(StrEnum):
    RECORDS = "records"
    LINKS = "record_links"
    UPLOADS = "uploads"
    VECTORS = "ograg_vectors"
    HYPERNODES = "ograg_hypernodes"
    FACTS = "ograg_facts"
    FACT_NODES = "ograg_fact_nodes"


class CommonColumn(StrEnum):
    ID = "id"
    RECORD_ID = "record_id"
    NODE_ID = "node_id"
    ANCHOR_ID = "anchor_id"
    LANE = "lane"
    VALUE = "value"
    POSITION = "position"


class SystemColumn(StrEnum):
    """Postgres system columns."""

    XMIN = "xmin"  # id of the transaction that wrote the row


class RecordColumn(StrEnum):
    CLS = "cls"
    GRAPH = "graph"
    INPUT = "input"
    ONTOLOGY_VERSION = "ontology_version"
    REVIEW = "review"
    UPDATED_AT = "updated_at"
    IDENTITY_VALUES = "identity_values"


class LinkColumn(StrEnum):
    PROPERTY_NAME = "property_name"
    TARGET_ID = "target_id"


class VectorColumn(StrEnum):
    KIND = "kind"
    MODEL = "model"
    EMBEDDING = "embedding"


class HypernodeColumn(StrEnum):
    KEY = "key"
    KEY_VID = "key_vid"
    VALUE_VID = "value_vid"
    LEXICAL = "lexical"


class FactColumn(StrEnum):
    SORT_KEY = "sort_key"
    TEXT = "text"


class FactNodeColumn(StrEnum):
    FACT_ID = "fact_id"


class UploadColumn(StrEnum):
    FILE_ID = "file_id"
    STATUS = "status"
    ERROR_CODE = "error_code"
    SOURCE_KEY = "source_key"
    PREVIEW_KEY = "preview_key"
    MODEL_KEY = "model_key"
    SIZE_BYTES = "size_bytes"
    SHA256 = "sha256"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class UploadStatus(StrEnum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


PROCESSING_INDEX: str = f"ix_{TableName.UPLOADS}_{UploadStatus.PROCESSING}"
STATUS_CHECK: str = f"ck_{TableName.UPLOADS}_{UploadColumn.STATUS}"
