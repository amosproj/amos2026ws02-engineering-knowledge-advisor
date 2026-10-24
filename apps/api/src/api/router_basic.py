from fastapi import APIRouter
from model import TestRequest, TestResponse

from api.router_builder import ApiRouterBuilder

v1_router: APIRouter = ApiRouterBuilder().version("v1").build()


@v1_router.post(
    "/ping",
    responses={
        200: {"model": TestResponse, "description": "Successful response"},
    },
)
def test_ping(body: TestRequest) -> TestResponse:
    """Sample ping-pong endpoint with request and response bodies."""
    return TestResponse(pong=body.ping + 1)
