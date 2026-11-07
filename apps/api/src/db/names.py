from enum import StrEnum


class TableName(StrEnum):
    RECORDS = "ograg_records"
    LINKS = "ograg_links"
    CAD_UPLOADS = "cad_uploads"


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


class CadUploadColumn(StrEnum):
    CAD_FILE_ID = "cad_file_id"
    STATUS = "status"
    ERROR_CODE = "error_code"
    SOURCE_KEY = "source_key"
    PREVIEW_KEY = "preview_key"
    MODEL_KEY = "model_key"
    SIZE_BYTES = "size_bytes"
    SHA256 = "sha256"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class CadUploadStatus(StrEnum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


SHA256_READY_INDEX: str = (
    f"uq_{TableName.CAD_UPLOADS}_{CadUploadColumn.SHA256}_{CadUploadStatus.READY}"
)
PROCESSING_INDEX: str = f"ix_{TableName.CAD_UPLOADS}_{CadUploadStatus.PROCESSING}"
STATUS_CHECK: str = f"ck_{TableName.CAD_UPLOADS}_{CadUploadColumn.STATUS}"
