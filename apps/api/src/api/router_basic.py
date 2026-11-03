from fastapi import APIRouter

from api.router_builder import ApiRouterBuilder
from model import TestRequest, TestResponse
from model.problem import Problem, ProblemException

RESPONSE_DETAIL_200: str = "Successful response."
RESPONSE_DETAIL_500: str = "Internal server error."
RESPONSE_DETAIL_422: str = "Request validation failed."
RESPONSE_DETAIL_429: str = "Too many requests."

basic_router: APIRouter = ApiRouterBuilder().version("v1").build()


@basic_router.post(
    "/ping",
    responses={
        200: {"model": TestResponse, "description": RESPONSE_DETAIL_200},
        500: {"model": Problem, "description": RESPONSE_DETAIL_500},
        422: {"model": Problem, "description": RESPONSE_DETAIL_422},
        429: {"model": Problem, "description": RESPONSE_DETAIL_429},
    },
)
def test_ping(body: TestRequest) -> TestResponse:
    """Sample ping-pong endpoint with request and response bodies."""
    if body.ping == 42:
        raise ProblemException(Problem.from_status(500, detail=RESPONSE_DETAIL_500))
    return TestResponse(pong=body.ping + 1)
