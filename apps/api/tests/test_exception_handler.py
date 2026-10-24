from typing import Any

import pytest
from httpx2 import Response

CONTENT_TYPE_PROBLEM_JSON: str = "application/problem+json"


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
