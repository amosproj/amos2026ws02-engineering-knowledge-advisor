from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.router_llm import llm_router
from handler import exception_handler, service_exception_handler
from services.llm.errors import ProviderRateLimitError
from services.llm.models import (
    ChatRequest,
    ChatResponse,
    ChatStreamChunk,
    ModelInfo,
    ProviderInfo,
)


class FakeLLMService:
    async def complete(self, request: ChatRequest) -> ChatResponse:
        if request.model == "rate-limited":
            raise ProviderRateLimitError()
        return ChatResponse(
            provider=request.provider or "openai",
            model=request.model or "test-model",
            content="Hello",
            finish_reason="stop",
            request_id="request-1",
        )

    async def _stream(self) -> AsyncIterator[ChatStreamChunk]:
        yield ChatStreamChunk(provider="openai", model="test-model", content="Hello")

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatStreamChunk]:
        del request
        return self._stream()

    def list_providers(self) -> list[ProviderInfo]:
        return [ProviderInfo(name="openai", default_model="test-model")]

    async def list_models(self, provider: str | None = None) -> list[ModelInfo]:
        return [ModelInfo(provider=provider or "openai", model="test-model")]


def build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(llm_router)
    app.state.llm = FakeLLMService()
    exception_handler.register(app)
    service_exception_handler.register(app)
    return app


def build_client() -> TestClient:
    return TestClient(build_app())


def test_chat_endpoint_returns_normalized_response() -> None:
    with build_client() as client:
        response = client.post(
            "/api/v1/llm/chat",
            json={
                "provider": "openai",
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )
    assert response.status_code == 200
    assert response.json() == {
        "provider": "openai",
        "model": "test-model",
        "content": "Hello",
        "finish_reason": "stop",
        "usage": None,
        "request_id": "request-1",
    }


def test_provider_and_model_endpoints_do_not_expose_secrets() -> None:
    with build_client() as client:
        providers = client.get("/api/v1/llm/providers")
        models = client.get("/api/v1/llm/models?provider=openai")
    assert providers.json() == [{"name": "openai", "default_model": "test-model"}]
    assert models.json() == [{"provider": "openai", "model": "test-model"}]


def test_stream_endpoint_uses_sse_and_normalized_chunks() -> None:
    with build_client() as client:
        response = client.post(
            "/api/v1/llm/chat/stream",
            json={
                "provider": "openai",
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert (
        'data: {"provider":"openai","model":"test-model","content":"Hello"'
        in response.text
    )
    assert "data: [DONE]" in response.text


def test_stream_openapi_declares_server_sent_events() -> None:
    response = build_app().openapi()["paths"]["/api/v1/llm/chat/stream"]["post"][
        "responses"
    ]["200"]

    assert "text/event-stream" in response["content"]


def test_llm_openapi_operations_have_descriptions() -> None:
    paths = build_app().openapi()["paths"]
    expected_descriptions = {
        ("/api/v1/llm/chat", "post"): (
            "Sends a chat request to an LLM provider and returns the completed response."
        ),
        ("/api/v1/llm/chat/stream", "post"): (
            "Streams a chat completion from an LLM provider as server-sent events."
        ),
        ("/api/v1/llm/providers", "get"): (
            "Lists configured LLM providers and their default models."
        ),
        ("/api/v1/llm/models", "get"): (
            "Lists models available from a provider, or from all providers when omitted."
        ),
    }

    for (path, method), description in expected_descriptions.items():
        assert paths[path][method]["description"] == description


def test_invalid_chat_body_uses_problem_response() -> None:
    with build_client() as client:
        response = client.post(
            "/api/v1/llm/chat",
            json={
                "provider": "openai",
                "temperature": 5,
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_provider_errors_use_problem_responses() -> None:
    with build_client() as client:
        response = client.post(
            "/api/v1/llm/chat",
            json={
                "provider": "openai",
                "model": "rate-limited",
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )
    assert response.status_code == 429
    assert response.json()["errorCode"] == "provider_rate_limited"
