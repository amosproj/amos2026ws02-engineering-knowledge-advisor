from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.router_builder import ApiRouterBuilder
from db.session import get_session
from model import RecordNode, Records, RecordsDeleted, RecordToReview, RecordWritten
from model.problem import Problem, ProblemException
from services import Record
from services.ograg.service import OgRagService

RECORD_ID_PATTERN: str = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
RECORD_ID_MAX_LENGTH: int = 200

RESPONSE_DETAIL_404: str = "No such record."
RESPONSE_DETAIL_409: str = "Concurrent write. Please try again."
RESPONSE_DETAIL_422_INVALID_ONTOLOGY: str = (
    "Does not fit ontology. Link target is missing, or value cannot be stored."
)
RESPONSE_DETAIL_422_INVALID_REQUEST: str = "Request validation failed."


v1_records_router: APIRouter = (
    ApiRouterBuilder().version("v1").add_tags(["records"]).build()
)


def get_service(request: Request) -> OgRagService:
    return request.app.state.ograg


def get_author() -> str | None:
    """``og:author`` property"""
    return None  # TODO: user-given str?


Service = Annotated[OgRagService, Depends(get_service)]
Session = Annotated[AsyncSession, Depends(get_session, scope="function")]
Author = Annotated[str | None, Depends(get_author)]
RecordId = Annotated[
    str, Path(pattern=RECORD_ID_PATTERN, max_length=RECORD_ID_MAX_LENGTH)
]


@v1_records_router.put(
    "/records/{record_id}",
    responses={
        422: {
            "model": Problem,
            "description": RESPONSE_DETAIL_422_INVALID_ONTOLOGY,
        },
        409: {
            "model": Problem,
            "description": RESPONSE_DETAIL_409,
        },
    },
)
async def put_record(
    record_id: RecordId,
    node: Annotated[RecordNode, Body()],
    service: Service,
    session: Session,
    author: Author,
) -> RecordWritten:
    """PUTs a record. Links hold target ids.

    ``@type`` defaults to anchor class.
    ``@id`` is ``record_id``.
    Link targets must already exist.
    """
    warnings = await service.upsert_record(record_id, node.to_node(), session, author)
    return RecordWritten(id=record_id, warnings=warnings)


@v1_records_router.get("/records")
async def get_records(service: Service, session: Session) -> Records:
    """All validated records by id. WARNING: reads EVERY record."""
    return Records.model_validate(await service.get_records(session))


@v1_records_router.get("/records/review")
async def get_records_to_review(
    service: Service, session: Session
) -> list[RecordToReview]:
    """Returns knowledge items whose assembly group was deleted."""
    return [
        RecordToReview(
            id=rec.id, review=rec.review, record=RecordNode.model_validate(rec.graph)
        )
        for rec in await service.get_records_to_review(session)
    ]


# keep this route under ``/records/review``, otherwise 'review' is interpreted as a ``record_id``
@v1_records_router.get(
    "/records/{record_id}",
    responses={
        404: {"model": Problem, "description": RESPONSE_DETAIL_404},
        422: {"model": Problem, "description": RESPONSE_DETAIL_422_INVALID_REQUEST},
    },
)
async def get_record(
    record_id: RecordId, service: Service, session: Session
) -> RecordNode:
    """Returns validated record. Links hold target ids."""
    record: Record | None = await service.get_record(record_id, session)
    if record is None:
        raise ProblemException(Problem.from_status(404, detail=RESPONSE_DETAIL_404))
    return RecordNode.model_validate(record.graph)


@v1_records_router.delete(
    "/records/{record_id}",
    responses={
        404: {"model": Problem, "description": RESPONSE_DETAIL_404},
        409: {
            "model": Problem,
            "description": RESPONSE_DETAIL_409,
        },
        422: {"model": Problem, "description": RESPONSE_DETAIL_422_INVALID_REQUEST},
    },
)
async def delete_record(
    record_id: RecordId,
    service: Service,
    session: Session,
    delete_orphans: bool = False,
) -> RecordsDeleted:
    """Delete a record and unlink it everywhere.

    Records left without a parent link are also deleted if ``delete_orphans`` is ``True``, otherwise marked for review.
    """
    result = await service.delete_record(record_id, session, delete_orphans)
    if not result.deleted_ids:
        raise ProblemException(Problem.from_status(404, detail=RESPONSE_DETAIL_404))
    return RecordsDeleted(deleted_ids=result.deleted_ids, marked_ids=result.marked_ids)
