from enum import StrEnum
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    Header,
    Path,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from api.router_builder import ApiRouterBuilder
from db.session import get_session
from model import (
    NO_FILE,
    FileUpload,
    RecordChanges,
    RecordNode,
    Records,
    RecordsDeleted,
    RecordToReview,
    RecordView,
    RecordWritten,
)
from model.problem import Problem
from services import Record
from services.catalog import CatalogService, CreatedRecord, DeletedRecords
from services.ograg.service import OgRagService
from services.uploads import Upload, UploadStatus

RECORD_ID_PATTERN: str = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
RECORD_ID_MAX_LENGTH: int = 200
ETAG_HEADER: str = "ETag"
WEAK_TAG_PREFIX: str = "W/"  # never matches If-Match (RFC 9110)


class Include(StrEnum):
    """Extras ``GET /records`` computes per record."""

    STATUS = "status"
    CHILDREN = "children"
    UPLOAD = "upload"


INCLUDE_NAMES: str = "|".join(Include)
INCLUDE_PATTERN: str = rf"^({INCLUDE_NAMES})(,({INCLUDE_NAMES}))*$"

RESPONSE_DETAIL_200_PUT: str = "Successfully stored record including validation drops."
RESPONSE_DETAIL_201_POST: str = "The new record's id including validation drops."
RESPONSE_DETAIL_200_PATCH: str = (
    "Successfully changed record including validation drops."
)
RESPONSE_DETAIL_200_GET_ALL: str = "All records sorted by their id."
RESPONSE_DETAIL_200_GET_REVIEW: str = "Records marked for manual user review."
RESPONSE_DETAIL_200_GET: str = "Requested record."
RESPONSE_DETAIL_200_DELETE: str = (
    "Successfully deleted record including record ids marked for review."
)
RESPONSE_DETAIL_404: str = "No such record."
RESPONSE_DETAIL_409: str = "Concurrent write. Please try again."
RESPONSE_DESCRIPTION_409: str = (
    "Concurrent write, or a file of the record is being processed. Please try again."
)
RESPONSE_DETAIL_422_INVALID_ONTOLOGY: str = (
    "Does not fit ontology. Link target is missing, or value cannot be stored."
)
RESPONSE_DETAIL_422_INVALID_REQUEST: str = "Request validation failed."
RESPONSE_DETAIL_412: str = "Record changed since the If-Match version. Read it again."
DESCRIPTION_IF_MATCH: str = (
    'Record version last read, e.g. "1234". Without it, nothing is checked.'
)

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": Problem, "description": RESPONSE_DETAIL_404},
    422: {"model": Problem, "description": RESPONSE_DETAIL_422_INVALID_REQUEST},
}
PRECONDITION_FAILED: dict[int | str, dict[str, Any]] = {
    412: {"model": Problem, "description": RESPONSE_DETAIL_412},
}


v1_records_router: APIRouter = (
    ApiRouterBuilder().version("v1").add_tags(["records"]).build()
)


def get_service(request: Request) -> OgRagService:
    return request.app.state.ograg


def get_catalog(request: Request) -> CatalogService:
    return request.app.state.catalog


def get_include(
    include: Annotated[
        str | None,
        Query(
            pattern=INCLUDE_PATTERN,
            description="Comma-separated extras per record.",
        ),
    ] = None,
) -> set[Include]:
    return set() if include is None else {Include(name) for name in include.split(",")}


def get_expected_versions(
    if_match: Annotated[str | None, Header(description=DESCRIPTION_IF_MATCH)] = None,
) -> list[str] | None:
    """Returns the versions in ``If-Match`` without weak tags, ``None`` without the header."""
    if if_match is None:
        return None
    tags: list[str] = [tag.strip() for tag in if_match.split(",")]
    return [tag.strip('"') for tag in tags if not tag.startswith(WEAK_TAG_PREFIX)]


Service = Annotated[OgRagService, Depends(get_service)]
Catalog = Annotated[CatalogService, Depends(get_catalog)]
Session = Annotated[AsyncSession, Depends(get_session, scope="function")]
Includes = Annotated[set[Include], Depends(get_include)]
ExpectedVersions = Annotated[list[str] | None, Depends(get_expected_versions)]
RecordId = Annotated[
    str,
    Path(alias="recordId", pattern=RECORD_ID_PATTERN, max_length=RECORD_ID_MAX_LENGTH),
]


@v1_records_router.post(
    "/records",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"model": RecordWritten, "description": RESPONSE_DETAIL_201_POST},
        422: {
            "model": Problem,
            "description": RESPONSE_DETAIL_422_INVALID_ONTOLOGY,
        },
        409: {"model": Problem, "description": RESPONSE_DETAIL_409},
    },
)
async def post_record(
    node: Annotated[RecordNode, Body()],
    catalog: Catalog,
    session: Session,
    response: Response,
) -> RecordWritten:
    """Creates a record with a generated id. Links hold target ids.

    ``@type`` defaults to anchor class. A sent ``@id`` is ignored.
    """
    created: CreatedRecord = await catalog.create_record(session, node.to_node())
    return _to_written(created.record, created.warnings, response)


@v1_records_router.put(
    "/records/{recordId}",
    responses={
        200: {"model": RecordWritten, "description": RESPONSE_DETAIL_200_PUT},
        422: {
            "model": Problem,
            "description": RESPONSE_DETAIL_422_INVALID_ONTOLOGY,
        },
        409: {
            "model": Problem,
            "description": RESPONSE_DETAIL_409,
        },
        **PRECONDITION_FAILED,
    },
)
async def put_record(
    record_id: RecordId,
    node: Annotated[RecordNode, Body()],
    service: Service,
    catalog: Catalog,
    session: Session,
    expected_versions: ExpectedVersions,
    response: Response,
) -> RecordWritten:
    """PUTs a record. Links hold target ids.

    ``@type`` defaults to anchor class.
    ``@id`` is ``record_id``.
    Link targets must already exist.
    """
    warnings: list[str] = await service.upsert_record(
        record_id, node.to_node(), session, expected_versions
    )
    written: Record = await catalog.get_record(session, record_id)
    return _to_written(written, warnings, response)


@v1_records_router.patch(
    "/records/{recordId}",
    responses={
        200: {"model": RecordWritten, "description": RESPONSE_DETAIL_200_PATCH},
        404: {"model": Problem, "description": RESPONSE_DETAIL_404},
        422: {
            "model": Problem,
            "description": RESPONSE_DETAIL_422_INVALID_ONTOLOGY,
        },
        409: {"model": Problem, "description": RESPONSE_DETAIL_409},
        **PRECONDITION_FAILED,
    },
)
async def patch_record(
    record_id: RecordId,
    changes: Annotated[RecordChanges, Body()],
    catalog: Catalog,
    session: Session,
    expected_versions: ExpectedVersions,
    response: Response,
) -> RecordWritten:
    """Executes JSON Merge Patch (https://www.rfc-editor.org/info/rfc7396/).
    Whole record is validated again as with PUT.
    """
    warnings: list[str] = await catalog.update_record(
        session, record_id, changes.root, expected_versions
    )
    written: Record = await catalog.get_record(session, record_id)
    return _to_written(written, warnings, response)


@v1_records_router.get(
    "/records",
    response_model_exclude_unset=True,
    responses={
        # model comes from the return type, a union listed twice otherwise
        200: {"description": RESPONSE_DETAIL_200_GET_ALL},
        422: {"model": Problem, "description": RESPONSE_DETAIL_422_INVALID_REQUEST},
    },
)
async def get_records(
    catalog: Catalog,
    session: Session,
    include: Includes,
    cls: Annotated[str | None, Query(description="Only records of this class.")] = None,
    parent_id: Annotated[
        str | None,
        Query(
            alias="parentId",
            description="Only records with a parent link to this parent id.",
        ),
    ] = None,
) -> Records | list[RecordView]:
    """All validated records by id. WARNING: reads EVERY record."""
    found: list[Record] = await catalog.get_records(session, cls, parent_id)
    if not include:
        return Records([to_node(rec) for rec in found])
    return [await _to_view(catalog, session, rec, include) for rec in found]


@v1_records_router.get(
    "/records/review",
    responses={
        200: {
            "model": list[RecordToReview],
            "description": RESPONSE_DETAIL_200_GET_REVIEW,
        },
    },
)
async def get_records_to_review(
    service: Service, session: Session
) -> list[RecordToReview]:
    """Returns knowledge items whose assembly group was deleted."""
    return [
        RecordToReview(
            id=rec.id,
            review=rec.review,
            record=RecordNode.model_validate(rec.graph),
            version=rec.version,
        )
        for rec in await service.get_records_to_review(session)
    ]


# keep this route under ``/records/review``, otherwise 'review' is interpreted as a ``record_id``
@v1_records_router.get(
    "/records/{recordId}",
    response_model_exclude_unset=True,
    responses={
        200: {"description": RESPONSE_DETAIL_200_GET},
        **NOT_FOUND,
    },
)
async def get_record(
    record_id: RecordId,
    catalog: Catalog,
    session: Session,
    include: Includes,
    response: Response,
) -> RecordNode | RecordView:
    """Returns validated record. Links hold target ids."""
    record: Record = await catalog.get_record(session, record_id)
    response.headers[ETAG_HEADER] = to_etag(record.version)
    if not include:
        return to_node(record)
    return await _to_view(catalog, session, record, include)


@v1_records_router.delete(
    "/records/{recordId}",
    responses={
        200: {"model": RecordsDeleted, "description": RESPONSE_DETAIL_200_DELETE},
        409: {
            "model": Problem,
            "description": RESPONSE_DESCRIPTION_409,
        },
        **NOT_FOUND,
        **PRECONDITION_FAILED,
    },
)
async def delete_record(
    record_id: RecordId,
    catalog: Catalog,
    session: Session,
    background_tasks: BackgroundTasks,
    expected_versions: ExpectedVersions,
    delete_orphans: Annotated[bool, Query(alias="deleteOrphans")] = False,
) -> RecordsDeleted:
    """Deletes a record and unlinks it everywhere.

    Records left without a parent link are also deleted if ``delete_orphans`` is ``True``, otherwise marked for review.
    Records whose parent link is marked ``og:deleteWithParent`` are deleted with it.
    """
    deleted: DeletedRecords = await catalog.delete_record(
        session, record_id, delete_orphans, expected_versions
    )
    background_tasks.add_task(catalog.delete_source_folders, deleted.source_keys)
    return RecordsDeleted(
        deleted_ids=deleted.deleted_ids, marked_ids=deleted.marked_ids
    )


async def _to_view(
    catalog: CatalogService, session: Session, record: Record, include: set[Include]
) -> RecordView:
    view = RecordView(record=to_node(record), version=record.version)
    if Include.STATUS in include and catalog.has_status(record):
        file_status: UploadStatus | None = await catalog.get_status(session, record.id)
        view.status = NO_FILE if file_status is None else file_status
    if Include.CHILDREN in include:
        children: list[Record] = await catalog.get_children(session, record.id)
        view.children = [to_node(child) for child in children]
    if Include.UPLOAD in include and catalog.is_file_record(record):
        upload: Upload | None = await catalog.get_upload(session, record.id)
        view.upload = None if upload is None else to_file_upload(upload)
    return view


def to_node(record: Record) -> RecordNode:
    return RecordNode.model_validate(record.graph)


def to_etag(version: str) -> str:
    """Returns ``version`` as entity tag, e.g. ``"1234"``."""
    return f'"{version}"'


def _to_written(
    record: Record, warnings: list[str], response: Response
) -> RecordWritten:
    response.headers[ETAG_HEADER] = to_etag(record.version)
    return RecordWritten(id=record.id, warnings=warnings, version=record.version)


def to_file_upload(upload: Upload) -> FileUpload:
    return FileUpload(
        id=upload.file_id,
        status=upload.status,
        error_code=upload.error_code,
        size_bytes=upload.size_bytes,
        created_at=upload.created_at,
        updated_at=upload.updated_at,
    )
