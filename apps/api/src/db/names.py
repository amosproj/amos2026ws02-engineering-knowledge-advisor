from enum import StrEnum


class TableName(StrEnum):
    RECORDS = "records"
    LINKS = "record_links"
    UPLOADS = "uploads"


class CommonColumn(StrEnum):
    ID = "id"
    RECORD_ID = "record_id"


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
    POSITION = "position"
    PROPERTY_NAME = "property_name"
    TARGET_ID = "target_id"


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
