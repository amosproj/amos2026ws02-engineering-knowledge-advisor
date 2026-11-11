from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr, ValidationError

from config.settings import LLMProviderSettings, Settings
from services.llm.errors import (
    InvalidLLMRequestError,
    InvalidProviderError,
    ProviderDisabledError,
)
from services.llm.models import ChatMessage, ChatRequest
from services.llm.service import ConfiguredLLMService


def build_settings(
    *,
    default_provider: str | None = None,
    openai: LLMProviderSettings | None = None,
    hetzner: LLMProviderSettings | None = None,
) -> Settings:
    return Settings(
        ograg_ontology_path=Path("unused.jsonld"),
        s3_endpoint_url="http://localhost:9000",
        s3_bucket="test",
        s3_access_key="test",
        s3_secret_key=SecretStr("test"),
        s3_region="us-east-1",
        s3_public_url="/storage",
        llm_default_provider=default_provider,
        llm_openai=openai or LLMProviderSettings(),
        llm_ollama=LLMProviderSettings(),
        llm_hetzner=hetzner or LLMProviderSettings(),
    )


def chat_request(**values: object) -> ChatRequest:
    request: dict[str, object] = {
        "messages": [ChatMessage(role="user", content="Hello")],
    }
    request.update(values)
    return ChatRequest.model_validate(request)


def test_system_messages_must_precede_conversation_history() -> None:
    with pytest.raises(ValidationError):
        chat_request(
            messages=[
                ChatMessage(role="user", content="Hello"),
                ChatMessage(role="system", content="Be brief"),
            ]
        )


@pytest.mark.anyio
async def test_default_provider_and_model_are_resolved() -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["authorization"] == "Bearer test-key"
        assert b'"model":"configured-model"' in request.content
        return httpx2.Response(
            200,
            json={
                "id": "request-123",
                "choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}],
            },
        )

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
    service = ConfiguredLLMService(
        build_settings(
            default_provider="openai",
            openai=LLMProviderSettings(
                enabled=True,
                api_key=SecretStr("test-key"),
                default_model="configured-model",
            ),
        ),
        client,
    )
    try:
        response = await service.complete(chat_request())
        assert response.provider == "openai"
        assert response.model == "configured-model"
        assert response.content == "Hello"
        assert response.request_id == "request-123"
        assert service.list_providers()[0].default_model == "configured-model"
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_provider_selection_and_models_are_exposed_without_credentials() -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={"data": [{"id": "model-a"}, {"id": "model-b"}]},
        )

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
    service = ConfiguredLLMService(
        build_settings(
            openai=LLMProviderSettings(
                enabled=True,
                api_key=SecretStr("must-not-be-returned"),
                default_model="model-a",
            )
        ),
        client,
    )
    try:
        models = await service.list_models("openai")
        assert [model.model for model in models] == ["model-a", "model-b"]
        assert "must-not-be-returned" not in repr(service.list_providers())
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_missing_provider_is_an_explicit_request_error() -> None:
    service = ConfiguredLLMService(build_settings())
    try:
        with pytest.raises(InvalidLLMRequestError):
            service.stream(chat_request())
    finally:
        await service.close()


@pytest.mark.anyio
async def test_unknown_provider_is_rejected() -> None:
    service = ConfiguredLLMService(build_settings())
    try:
        with pytest.raises(InvalidProviderError):
            service.stream(chat_request(provider="unknown"))
    finally:
        await service.close()


@pytest.mark.anyio
async def test_disabled_provider_is_rejected() -> None:
    service = ConfiguredLLMService(build_settings())
    try:
        with pytest.raises(ProviderDisabledError):
            service.stream(chat_request(provider="openai"))
    finally:
        await service.close()


@pytest.mark.anyio
async def test_hetzner_provider_is_resolved_and_model_can_be_selected() -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        assert request.url.host == "inference.hetzner.com"
        assert request.url.path.endswith("/chat/completions")
        assert b'"model":"Qwen/Qwen3.8-27B"' in request.content
        return httpx2.Response(
            200,
            json={
                "choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}]
            },
        )

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
    service = ConfiguredLLMService(
        build_settings(
            default_provider="hetzner",
            hetzner=LLMProviderSettings(
                enabled=True,
                api_key=SecretStr("test-token"),
                default_model="Qwen/Qwen3.6-35B-A3B-FP8",
            ),
        ),
        client,
    )
    try:
        result = await service.complete(chat_request(model="Qwen/Qwen3.8-27B"))
        assert result.provider == "hetzner"
        assert result.model == "Qwen/Qwen3.8-27B"
        assert result.content == "Hello"
    finally:
        await client.aclose()
