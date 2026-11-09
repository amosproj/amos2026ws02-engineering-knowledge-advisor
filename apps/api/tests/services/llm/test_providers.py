import asyncio
import json
from collections.abc import AsyncIterator

import httpx2
import pytest
from pydantic import SecretStr

from config.settings import LLMProviderSettings
from services.llm_impl.errors import (
    ContextLengthError,
    InvalidLLMRequestError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    StreamingInterruptedError,
    UnsupportedModelError,
)
from services.llm_impl.models import ChatMessage, ChatRequest, ChatStreamChunk
from services.llm_impl.providers import (
    AnthropicProvider,
    AzureOpenAIProvider,
    GoogleProvider,
    HetznerProvider,
    HTTPProvider,
    MistralProvider,
    OllamaProvider,
    OpenAIProvider,
)

type ProviderCase = tuple[str, type[HTTPProvider], dict[str, object], str]

PROVIDER_CASES: list[ProviderCase] = [
    (
        "hetzner",
        HetznerProvider,
        {
            "id": "request-hetzner",
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
        "/chat/completions",
    ),
    (
        "openai",
        OpenAIProvider,
        {
            "id": "request-1",
            "choices": [
                {
                    "message": {"content": "hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
            },
        },
        "/chat/completions",
    ),
    (
        "mistral",
        MistralProvider,
        {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
        "/chat/completions",
    ),
    (
        "azure_openai",
        AzureOpenAIProvider,
        {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
        "/openai/deployments/requested-model/chat/completions",
    ),
    (
        "anthropic",
        AnthropicProvider,
        {
            "id": "message-1",
            "content": [{"type": "text", "text": "hello"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 3, "output_tokens": 2},
        },
        "/messages",
    ),
    (
        "google",
        GoogleProvider,
        {
            "candidates": [
                {
                    "content": {"parts": [{"text": "hello"}]},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 3,
                "candidatesTokenCount": 2,
                "totalTokenCount": 5,
            },
        },
        "/models/requested-model:generateContent",
    ),
    (
        "ollama",
        OllamaProvider,
        {
            "message": {"content": "hello"},
            "done_reason": "stop",
            "prompt_eval_count": 3,
            "eval_count": 2,
        },
        "/api/chat",
    ),
]


def build_config() -> LLMProviderSettings:
    return LLMProviderSettings(
        enabled=True,
        api_key=SecretStr("test-key"),
        base_url="https://provider.test",
        default_model="configured-model",
    )


def build_request(**kwargs: object) -> ChatRequest:
    values: dict[str, object] = {
        "messages": [
            ChatMessage(role="system", content="be concise"),
            ChatMessage(role="user", content="say hello"),
        ]
    }
    values.update(kwargs)
    return ChatRequest.model_validate(values)


@pytest.mark.anyio
@pytest.mark.parametrize(("name", "provider_type", "body", "path"), PROVIDER_CASES)
async def test_providers_normalize_completions(
    name: str,
    provider_type: type[HTTPProvider],
    body: dict[str, object],
    path: str,
) -> None:
    sent: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        return httpx2.Response(200, json=body)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
    provider = provider_type(build_config(), client)
    try:
        result = await provider.complete(build_request(), "requested-model")
    finally:
        await client.aclose()

    assert result.provider == name
    assert result.model == "requested-model"
    assert result.content == "hello"
    assert result.finish_reason == "stop"
    assert result.usage is not None
    assert result.usage.prompt_tokens == 3
    assert result.usage.completion_tokens == 2
    assert sent[0].url.path.endswith(path)
    if name == "azure_openai":
        assert sent[0].headers["api-key"] == "test-key"
        assert "model" not in json.loads(sent[0].content)
    elif name == "anthropic":
        assert sent[0].headers["x-api-key"] == "test-key"
        payload = json.loads(sent[0].content)
        assert payload["system"] == "be concise"
        assert payload["messages"][0]["role"] == "user"
    elif name == "google":
        assert sent[0].url.params["key"] == "test-key"
        assert json.loads(sent[0].content)["systemInstruction"]
    else:
        assert sent[0].headers["authorization"] == "Bearer test-key"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_type", "body", "expected"),
    [
        (HetznerProvider, {"data": [{"id": "model-a"}]}, ["model-a"]),
        (OpenAIProvider, {"data": [{"id": "model-a"}]}, ["model-a"]),
        (MistralProvider, {"data": [{"id": "model-a"}]}, ["model-a"]),
        (AnthropicProvider, {"data": [{"id": "model-a"}]}, ["model-a"]),
        (
            GoogleProvider,
            {
                "models": [
                    {
                        "name": "models/model-a",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/embedding-a",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            },
            ["model-a"],
        ),
        (OllamaProvider, {"models": [{"name": "model-a:latest"}]}, ["model-a:latest"]),
    ],
)
async def test_provider_model_lists_are_normalized(
    provider_type: type[HTTPProvider],
    body: dict[str, object],
    expected: list[str],
) -> None:
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda request: httpx2.Response(200, json=body))
    )
    provider = provider_type(build_config(), client)
    try:
        assert await provider.list_models() == expected
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_hetzner_uses_documented_base_url_for_chat_and_models() -> None:
    sent: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        if request.url.path.endswith("/models"):
            return httpx2.Response(200, json={"data": [{"id": "model-a"}]})
        return httpx2.Response(
            200,
            json={"choices": [{"message": {"content": "hello"}}]},
        )

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
    provider = HetznerProvider(
        LLMProviderSettings(enabled=True, api_key=SecretStr("test-key")),
        client,
    )
    try:
        result = await provider.complete(build_request(), "model-a")
        models = await provider.list_models()
    finally:
        await client.aclose()

    assert result.provider == "hetzner"
    assert result.content == "hello"
    assert models == ["model-a"]
    assert json.loads(sent[0].content)["max_tokens"] == 4096
    assert [request.url for request in sent] == [
        httpx2.URL("https://inference.hetzner.com/api/v1/chat/completions"),
        httpx2.URL("https://inference.hetzner.com/api/v1/models"),
    ]
    assert all("authorization" in request.headers for request in sent)


def test_hetzner_preserves_an_explicit_output_token_limit() -> None:
    provider = HetznerProvider(build_config(), httpx2.AsyncClient())
    try:
        payload = provider._request_payload(build_request(max_tokens=512), "model")
    finally:
        asyncio.run(provider.client.aclose())

    assert payload["max_tokens"] == 512


def test_anthropic_merges_adjacent_messages_of_the_same_role() -> None:
    provider = AnthropicProvider(build_config(), httpx2.AsyncClient())
    try:
        payload = provider._request_payload(
            build_request(
                messages=[
                    ChatMessage(role="user", content="first"),
                    ChatMessage(role="user", content="second"),
                ]
            ),
            "model",
        )
    finally:
        asyncio.run(provider.client.aclose())
    assert payload["messages"] == [{"role": "user", "content": "first\n\nsecond"}]


@pytest.mark.anyio
async def test_azure_model_list_uses_configured_deployment() -> None:
    provider = AzureOpenAIProvider(
        LLMProviderSettings(
            enabled=True,
            api_key=SecretStr("test-key"),
            base_url="https://azure.test",
            default_model="deployment",
        ),
        httpx2.AsyncClient(),
    )
    try:
        assert await provider.list_models() == ["deployment"]
    finally:
        await provider.client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_type", "body", "expected_content"),
    [
        (
            HetznerProvider,
            'data: {"choices":[{"delta":{"content":"hi"},"finish_reason":null}]}\n\n',
            "hi",
        ),
        (
            OpenAIProvider,
            'data: {"choices":[{"delta":{"content":"hi"},"finish_reason":null}]}\n\n',
            "hi",
        ),
        (
            AnthropicProvider,
            'data: {"type":"content_block_delta","delta":{"text":"hi"}}\n\n',
            "hi",
        ),
        (
            GoogleProvider,
            'data: {"candidates":[{"content":{"parts":[{"text":"hi"}]}}]}\n\n',
            "hi",
        ),
        (
            OllamaProvider,
            '{"message":{"content":"hi"},"done":false}\n',
            "hi",
        ),
    ],
)
async def test_provider_stream_chunks_are_normalized(
    provider_type: type[HTTPProvider],
    body: str,
    expected_content: str,
) -> None:
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda request: httpx2.Response(200, text=body))
    )
    provider = provider_type(build_config(), client)
    try:
        chunks: list[ChatStreamChunk] = [
            chunk async for chunk in provider.stream(build_request(), "model")
        ]
    finally:
        await client.aclose()

    assert len(chunks) == 1
    assert chunks[0].content == expected_content
    assert chunks[0].model == "model"


@pytest.mark.anyio
async def test_mistral_stream_omits_empty_chunks_but_keeps_answer_and_finish() -> None:
    body = (
        'data: {"choices":[{"delta":{"role":"assistant","content":""},'
        '"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{"content":""},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda request: httpx2.Response(200, text=body))
    )
    provider = MistralProvider(build_config(), client)
    try:
        chunks = [chunk async for chunk in provider.stream(build_request(), "model")]
    finally:
        await client.aclose()

    assert [chunk.content for chunk in chunks] == ["Hello", ""]
    assert chunks[-1].finish_reason == "stop"


@pytest.mark.parametrize("reasoning_field", ["reasoning", "reasoning_content"])
def test_hetzner_stream_omits_private_reasoning_chunks(
    reasoning_field: str,
) -> None:
    provider = HetznerProvider(build_config(), httpx2.AsyncClient())
    try:
        reasoning_chunk = provider._parse_stream_data(
            json.dumps(
                {
                    "choices": [
                        {
                            "delta": {reasoning_field: "private reasoning"},
                            "finish_reason": None,
                        }
                    ],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 1},
                }
            ),
            build_request(),
            "model",
        )
        initial_chunk = provider._parse_stream_data(
            '{"choices":[{"delta":{"role":"assistant","content":""},"finish_reason":null}]}',
            build_request(),
            "model",
        )
        usage_only_chunk = provider._parse_stream_data(
            '{"choices":[],"usage":{"prompt_tokens":2,"completion_tokens":3,"total_tokens":5}}',
            build_request(),
            "model",
        )
        answer_chunk = provider._parse_stream_data(
            '{"choices":[{"delta":{"content":"Answer"},"finish_reason":null}]}',
            build_request(),
            "model",
        )
        finish_chunk = provider._parse_stream_data(
            '{"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":2,"completion_tokens":3,"total_tokens":5}}',
            build_request(),
            "model",
        )
    finally:
        asyncio.run(provider.client.aclose())

    assert reasoning_chunk is None
    assert initial_chunk is None
    assert usage_only_chunk is None
    assert answer_chunk is not None
    assert answer_chunk.content == "Answer"
    assert finish_chunk is not None
    assert finish_chunk.finish_reason == "stop"
    assert finish_chunk.usage is not None
    assert finish_chunk.usage.total_tokens == 5


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status_code", "message", "error"),
    [
        (401, "unauthorized", ProviderAuthenticationError),
        (429, "rate limited", ProviderRateLimitError),
        (404, "model not found", UnsupportedModelError),
        (400, "model does not exist", UnsupportedModelError),
        (413, "too large", ContextLengthError),
        (400, "context length exceeded", ContextLengthError),
        (400, "invalid request", InvalidLLMRequestError),
    ],
)
async def test_provider_errors_are_normalized(
    status_code: int,
    message: str,
    error: type[Exception],
) -> None:
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda request: httpx2.Response(status_code, text=message)
        )
    )
    provider = OpenAIProvider(build_config(), client)
    try:
        with pytest.raises(error):
            await provider.complete(build_request(), "model")
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_provider_timeout_is_normalized() -> None:
    def timeout(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectTimeout("timeout", request=request)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(timeout))
    provider = OpenAIProvider(build_config(), client)
    try:
        with pytest.raises(ProviderTimeoutError):
            await provider.complete(build_request(), "model")
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_generation_errors_are_not_retried() -> None:
    attempts: int = 0

    def unavailable(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        return httpx2.Response(503)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(unavailable))
    provider = OpenAIProvider(build_config(), client)
    try:
        with pytest.raises(ProviderUnavailableError):
            await provider.complete(build_request(), "model")
        assert attempts == 1
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_malformed_stream_events_are_normalized() -> None:
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda request: httpx2.Response(200, text="data: {invalid}\n\n")
        )
    )
    provider = OpenAIProvider(build_config(), client)
    try:
        with pytest.raises(StreamingInterruptedError):
            _ = [chunk async for chunk in provider.stream(build_request(), "model")]
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_stream_connection_failure_is_provider_unavailable() -> None:
    def unavailable(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("unreachable", request=request)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(unavailable))
    provider = OpenAIProvider(build_config(), client)
    try:
        with pytest.raises(ProviderUnavailableError):
            _ = [chunk async for chunk in provider.stream(build_request(), "model")]
    finally:
        await client.aclose()


class BlockingStream(httpx2.AsyncByteStream):
    def __init__(self) -> None:
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_closing_stream_cancels_the_upstream_request() -> None:
    upstream = BlockingStream()
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda request: httpx2.Response(200, stream=upstream)
        )
    )
    provider = OpenAIProvider(build_config(), client)
    iterator = provider.stream(build_request(), "model")
    try:
        first = await anext(iterator)
        assert first.content == "first"
        await iterator.aclose()
        assert upstream.closed
    finally:
        await client.aclose()
