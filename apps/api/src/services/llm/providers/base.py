import json
from collections.abc import AsyncGenerator, Mapping
from typing import Protocol

import httpx2

from config.settings import LLMProviderSettings
from services.llm.errors import (
    ContextLengthError,
    InvalidLLMRequestError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    StreamingInterruptedError,
    UnsupportedModelError,
)
from services.llm.models import ChatRequest, ChatResponse, ChatStreamChunk, TokenUsage

ProviderName = str
_RESERVED_OPTIONS: frozenset[str] = frozenset(
    {
        "model",
        "messages",
        "stream",
        "temperature",
        "max_tokens",
        "max_completion_tokens",
        "top_p",
        "response_format",
    }
)


class LLMProvider(Protocol):
    name: ProviderName

    async def complete(self, request: ChatRequest, model: str) -> ChatResponse: ...

    def stream(
        self, request: ChatRequest, model: str
    ) -> AsyncGenerator[ChatStreamChunk]: ...

    async def list_models(self) -> list[str]: ...


class HTTPProvider:
    name: ProviderName
    default_max_tokens = 1024

    def __init__(
        self,
        config: LLMProviderSettings,
        client: httpx2.AsyncClient,
    ) -> None:
        self.config = config
        self.client = client

    def _base_url(self, default: str) -> str:
        return (self.config.base_url or default).rstrip("/")

    def _auth_headers(self) -> dict[str, str]:
        if self.config.api_key is None:
            return {}
        return {"Authorization": f"Bearer {self.config.api_key.get_secret_value()}"}

    def _options(
        self, reserved: frozenset[str] = _RESERVED_OPTIONS
    ) -> dict[str, str | int | float | bool]:
        return {
            name: value
            for name, value in self.config.options.items()
            if name not in reserved
        }

    def _request_payload(self, request: ChatRequest, model: str) -> dict[str, object]:
        max_tokens: int = (
            request.max_tokens
            if "max_tokens" in request.model_fields_set
            else self.default_max_tokens
        )
        payload: dict[str, object] = {
            "model": model,
            "messages": [message.model_dump() for message in request.messages],
            "stream": False,
            "max_tokens": max_tokens,
            **self._options(),
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def _post(
        self,
        url: str,
        request: ChatRequest,
        model: str,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        try:
            response = await self.client.post(
                url,
                json=self._request_payload(request, model),
                headers=dict(headers or {}),
                params=dict(params or {}),
                timeout=self.config.timeout_seconds,
            )
        except httpx2.TimeoutException as exc:
            raise ProviderTimeoutError() from exc
        except httpx2.RequestError as exc:
            raise ProviderUnavailableError() from exc
        self._raise_for_status(response)
        return response

    async def _get(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        try:
            response = await self.client.get(
                url,
                headers=dict(headers or {}),
                params=dict(params or {}),
                timeout=self.config.timeout_seconds,
            )
        except httpx2.TimeoutException as exc:
            raise ProviderTimeoutError() from exc
        except httpx2.RequestError as exc:
            raise ProviderUnavailableError() from exc
        self._raise_for_status(response)
        return response

    @staticmethod
    def _raise_for_status(response: httpx2.Response) -> None:
        if response.is_success:
            return
        detail: str = ""
        try:
            detail = response.text.casefold()
        except (UnicodeDecodeError, ValueError):
            pass

        if response.status_code in (401, 403):
            raise ProviderAuthenticationError()
        if response.status_code == 429:
            raise ProviderRateLimitError()
        if response.status_code in (408, 504):
            raise ProviderTimeoutError()
        if response.status_code == 404 or (
            "model" in detail
            and any(
                phrase in detail
                for phrase in ("not found", "does not exist", "unsupported")
            )
        ):
            raise UnsupportedModelError()
        if response.status_code in (400, 413) and any(
            word in detail for word in ("context", "token limit", "too many tokens")
        ):
            raise ContextLengthError()
        if response.status_code == 413:
            raise ContextLengthError()
        if response.status_code in (400, 422):
            raise InvalidLLMRequestError()
        if response.status_code >= 500:
            raise ProviderUnavailableError()
        raise InvalidLLMRequestError()

    @staticmethod
    def _json(response: httpx2.Response) -> dict[str, object]:
        try:
            data: object = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise ProviderUnavailableError(
                "The LLM provider returned an invalid response."
            ) from exc
        if not isinstance(data, dict):
            raise ProviderUnavailableError(
                "The LLM provider returned an invalid response."
            )
        return data

    @staticmethod
    def _string(value: object) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _finish_reason(value: object) -> str | None:
        reason: str | None = HTTPProvider._string(value)
        if reason is None:
            return None
        normalized: str = reason.casefold()
        return {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "max_tokens": "length",
            "max_output_tokens": "length",
            "safety": "content_filter",
            "recitation": "content_filter",
            "tool_use": "tool_calls",
        }.get(normalized, normalized)

    @staticmethod
    def _content(value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "".join(
                part["text"]
                for part in value
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
        return ""

    @staticmethod
    def _usage(value: object) -> TokenUsage | None:
        if not isinstance(value, dict):
            return None
        prompt = value.get("prompt_tokens", value.get("input_tokens"))
        completion = value.get("completion_tokens", value.get("output_tokens"))
        total = value.get("total_tokens")
        return TokenUsage(
            prompt_tokens=prompt if isinstance(prompt, int) else None,
            completion_tokens=completion if isinstance(completion, int) else None,
            total_tokens=total if isinstance(total, int) else None,
        )

    def _normalized_response(
        self,
        data: dict[str, object],
        request: ChatRequest,
        model: str,
    ) -> ChatResponse:
        raise NotImplementedError

    async def complete(self, request: ChatRequest, model: str) -> ChatResponse:
        response: httpx2.Response = await self._post(
            self.completions_url(model), request, model, self.completion_headers()
        )
        return self._normalized_response(self._json(response), request, model)

    def completions_url(self, model: str) -> str:
        raise NotImplementedError

    def completion_headers(self) -> dict[str, str]:
        return self._auth_headers()

    async def list_models(self) -> list[str]:
        return []

    def stream(
        self, request: ChatRequest, model: str
    ) -> AsyncGenerator[ChatStreamChunk]:
        return self._stream(request, model)

    async def _stream(
        self, request: ChatRequest, model: str
    ) -> AsyncGenerator[ChatStreamChunk]:
        response_received: bool = False
        try:
            async with self.client.stream(
                "POST",
                self.completions_url(model),
                json={**self._request_payload(request, model), "stream": True},
                headers=self.completion_headers(),
                timeout=self.config.timeout_seconds,
            ) as response:
                response_received = True
                if not response.is_success:
                    await response.aread()
                    self._raise_for_status(response)
                async for line in response.aiter_lines():
                    chunk: ChatStreamChunk | None = self._parse_stream_line(
                        line, request, model
                    )
                    if chunk is not None:
                        yield chunk
        except httpx2.TimeoutException as exc:
            raise ProviderTimeoutError() from exc
        except httpx2.RequestError as exc:
            if not response_received:
                raise ProviderUnavailableError() from exc
            raise StreamingInterruptedError() from exc

    def _parse_stream_line(
        self, line: str, request: ChatRequest, model: str
    ) -> ChatStreamChunk | None:
        if not line.startswith("data:"):
            return None
        data: str = line[5:].strip()
        if data == "[DONE]":
            return None
        return self._parse_stream_data(data, request, model)

    def _parse_stream_data(
        self, data: str, request: ChatRequest, model: str
    ) -> ChatStreamChunk | None:
        raise NotImplementedError

    def _chunk(
        self,
        content: str = "",
        finish_reason: str | None = None,
        usage: TokenUsage | None = None,
        model: str = "",
    ) -> ChatStreamChunk:
        return ChatStreamChunk(
            provider=self.name,
            model=model,
            content=content,
            finish_reason=finish_reason,
            usage=usage,
        )
