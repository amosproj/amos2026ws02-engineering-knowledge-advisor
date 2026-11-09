from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from api.router_records import RESPONSE_DETAIL_422_INVALID_REQUEST
from logger import logger
from model.problem import ProblemException, ProblemResponse

LOG_UNHANDLED: str = "Unhandled exception"


async def handle_problem(request: Request, exc: ProblemException) -> ProblemResponse:
    problem = exc.problem
    if problem.instance is None:
        problem = problem.model_copy(update={"instance": request.url.path})
    return ProblemResponse(problem, headers=exc.headers)


async def handle_http(request: Request, exc: HTTPException) -> ProblemResponse:
    detail = exc.detail if isinstance(exc.detail, str) else None
    return ProblemResponse.from_status(
        exc.status_code, detail, instance=request.url.path, headers=exc.headers
    )


async def handle_validation(
    request: Request, exc: RequestValidationError
) -> ProblemResponse:
    return ProblemResponse.from_status(
        422,
        RESPONSE_DETAIL_422_INVALID_REQUEST,
        instance=request.url.path,
        errors=exc.errors(),
    )


async def handle_unexpected(request: Request, exc: Exception) -> ProblemResponse:
    logger.exception(LOG_UNHANDLED, exc_info=exc)
    return ProblemResponse.from_status(500, instance=request.url.path)


def register(app: FastAPI) -> None:
    app.exception_handler(ProblemException)(handle_problem)
    app.exception_handler(HTTPException)(handle_http)
    app.exception_handler(RequestValidationError)(handle_validation)
    app.exception_handler(Exception)(handle_unexpected)
