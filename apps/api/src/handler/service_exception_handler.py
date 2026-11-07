from fastapi import FastAPI, Request

from api.router_files import RESPONSE_DETAIL_503
from logger import logger
from model.problem import ProblemResponse
from services import ConflictError, StaleVersionError, UnstorableValueError
from services.catalog import CadFileConflictError, NotFoundError
from services.object_storage import ObjectStorageError
from services.ograg.service import RecordError

LOG_FAILED_CONVERSION: str = "Could not convert exception to response detail"
LOG_STORAGE_UNAVAILABLE: str = "The object storage failed"


def _to_response_detail(exc: Exception) -> str:
    """Returns exception message as response detail. First letter capitalized, ends with a period."""
    message: str = str(exc).strip()
    if not message:
        logger.exception(LOG_FAILED_CONVERSION, exc_info=exc)
        return message
    detail: str = message[0].upper() + message[1:]
    return detail if detail.endswith((".", "!", "?")) else f"{detail}."


async def handle_unprocessable(request: Request, exc: Exception) -> ProblemResponse:
    return ProblemResponse.from_status(
        422, _to_response_detail(exc), instance=request.url.path
    )


async def handle_conflict(request: Request, exc: Exception) -> ProblemResponse:
    return ProblemResponse.from_status(
        409, _to_response_detail(exc), instance=request.url.path
    )


async def handle_cad_file_conflict(
    request: Request, exc: CadFileConflictError
) -> ProblemResponse:
    return ProblemResponse.from_status(
        409,
        _to_response_detail(exc),
        error_code=exc.error_code,
        instance=request.url.path,
    )


async def handle_precondition_failed(
    request: Request, exc: Exception
) -> ProblemResponse:
    return ProblemResponse.from_status(
        412, _to_response_detail(exc), instance=request.url.path
    )


async def handle_not_found(request: Request, exc: Exception) -> ProblemResponse:
    return ProblemResponse.from_status(
        404, _to_response_detail(exc), instance=request.url.path
    )


async def handle_storage_unavailable(
    request: Request, exc: Exception
) -> ProblemResponse:
    logger.warning(LOG_STORAGE_UNAVAILABLE, exc_info=exc)
    return ProblemResponse.from_status(
        503, RESPONSE_DETAIL_503, instance=request.url.path
    )


def register(app: FastAPI) -> None:
    app.exception_handler(RecordError)(handle_unprocessable)
    app.exception_handler(UnstorableValueError)(handle_unprocessable)
    app.exception_handler(ConflictError)(handle_conflict)
    app.exception_handler(CadFileConflictError)(handle_cad_file_conflict)
    app.exception_handler(NotFoundError)(handle_not_found)
    app.exception_handler(StaleVersionError)(handle_precondition_failed)
    app.exception_handler(ObjectStorageError)(handle_storage_unavailable)
