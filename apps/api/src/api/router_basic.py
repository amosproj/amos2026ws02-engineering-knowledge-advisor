from fastapi import APIRouter

from api.router_builder import ApiRouterBuilder
from model import TestRequest, TestResponse
from model.problem import Problem, ProblemException

v1_router: APIRouter = ApiRouterBuilder().version("v1").build()


@v1_router.post(
    "/ping",
    responses={
        200: {"model": TestResponse, "description": "Successful response"},
        500: {"model": Problem, "description": "Internal server error"},
        422: {"model": Problem, "description": "Request body validation error"},
        429: {"model": Problem, "description": "Too many requests"},
    },
)
def test_ping(body: TestRequest) -> TestResponse:
    """Sample ping-pong endpoint with request and response bodies."""
    if body.ping == 42:
        raise ProblemException(Problem.from_status(500, detail="Internal server error"))
    return TestResponse(pong=body.ping + 1)
