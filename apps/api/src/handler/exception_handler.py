from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from model.problem import ProblemException, ProblemResponse
from starlette.exceptions import HTTPException


async def handle_problem(request: Request, e: ProblemException) -> ProblemResponse:
    problem = e.problem
    if problem.instance is None:
        problem = problem.model_copy(update={"instance": request.url.path})
    return ProblemResponse(problem, headers=e.headers)


async def handle_http(request: Request, e: HTTPException) -> ProblemResponse:
    detail = e.detail if isinstance(e.detail, str) else None
    return ProblemResponse.from_status(
        e.status_code, detail, instance=request.url.path, headers=e.headers
    )


async def handle_validation(
    request: Request, e: RequestValidationError
) -> ProblemResponse:
    return ProblemResponse.from_status(
        422, "Request validation failed", instance=request.url.path, errors=e.errors()
    )


def register(app: FastAPI) -> None:
    app.exception_handler(ProblemException)(handle_problem)
    app.exception_handler(HTTPException)(handle_http)
    app.exception_handler(RequestValidationError)(handle_validation)
