import logging
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response

from handler import register
from model.problem import Problem, ProblemResponse

CONTENT_TYPE_PROBLEM_JSON: str = "application/problem+json"

UNHANDLED_LOGGER_ID: str = "uvicorn.error"
UNHANDLED_LOG_MESSAGE: str = "Unhandled exception"


@pytest.mark.parametrize(
    ("request_endpoint", "request_body", "expected_status"),
    [
        ("/api/v1/ping", {"ping": 42}, 500),
        ("/api/v1/ping", {"ping": "nan"}, 422),
        ("/does/not/exist", "any", 404),
    ],
)
def test_handler(
    client, request_endpoint: str, request_body: dict[str, Any], expected_status: int
):
    response: Response = client.post(request_endpoint, json=request_body)
    assert response.status_code == expected_status
    assert response.headers["content-type"] == CONTENT_TYPE_PROBLEM_JSON

    response_body: dict[str, Any] = response.json()
    assert response_body["status"] == expected_status
    assert response_body["instance"] == request_endpoint


def test_unhandled(caplog: pytest.LogCaptureFixture):
    app = FastAPI()
    register(app)

    test_endpoint: str = "/kaboom"

    @app.post(test_endpoint)
    def kaboom() -> None:
        raise ValueError()

    with (
        caplog.at_level(logging.ERROR, logger=UNHANDLED_LOGGER_ID),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response: Response = client.post(test_endpoint)

    expected_status: int = 500

    # headers
    assert response.status_code == expected_status
    assert response.headers["content-type"] == CONTENT_TYPE_PROBLEM_JSON

    # body
    response_body: dict[str, Any] = response.json()
    assert response_body["status"] == expected_status
    assert response_body["instance"] == test_endpoint

    # logged by logger
    errors = [e for e in caplog.records if e.name == UNHANDLED_LOGGER_ID]
    assert errors and errors[0].message == UNHANDLED_LOG_MESSAGE
    assert errors[0].exc_info is not None


def test_problem_response_do_not_modify_problem_by_ref():
    problem = Problem(detail="My detail")  # status=None
    response = ProblemResponse(problem)  # sets status
    assert problem.status is None
    assert response.status_code == 500
