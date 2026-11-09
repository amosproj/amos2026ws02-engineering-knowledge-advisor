import json
from collections.abc import AsyncGenerator, Mapping
from typing import Protocol
from urllib.parse import quote
from uuid import uuid4

import httpx2

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
from services.llm_impl.models import (
    ChatRequest,
    ChatResponse,
    ChatStreamChunk,
    TokenUsage,
)

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


class OpenAIProvider(HTTPProvider):
    name = "openai"
    default_base_url = "https://api.openai.com/v1"

    def completions_url(self, model: str) -> str:
        del model
        return f"{self._base_url(self.default_base_url)}/chat/completions"

    def _normalized_response(
        self, data: dict[str, object], request: ChatRequest, model: str
    ) -> ChatResponse:
        del request
        choices: object = data.get("choices")
        choice: object = choices[0] if isinstance(choices, list) and choices else None
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            raise ProviderUnavailableError(
                "The LLM provider returned an invalid response."
            )
        message: dict[str, object] = choice["message"]
        return ChatResponse(
            provider=self.name,
            model=model,
            content=self._content(message.get("content")),
            finish_reason=self._finish_reason(choice.get("finish_reason")),
            usage=self._usage(data.get("usage")),
            request_id=self._string(data.get("id")) or uuid4().hex,
        )

    async def list_models(self) -> list[str]:
        data: dict[str, object] = self._json(
            await self._get(
                f"{self._base_url(self.default_base_url)}/models",
                self._auth_headers(),
            )
        )
        models: object = data.get("data")
        return (
            sorted(
                item["id"]
                for item in models
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            )
            if isinstance(models, list)
            else []
        )

    def _parse_stream_data(
        self, data: str, request: ChatRequest, model: str
    ) -> ChatStreamChunk | None:
        del request
        try:
            payload: object = json.loads(data)
        except json.JSONDecodeError as exc:
            raise StreamingInterruptedError() from exc
        if not isinstance(payload, dict):
            return None
        choices: object = payload.get("choices")
        choice: object = choices[0] if isinstance(choices, list) and choices else None
        if not isinstance(choice, dict):
            return None
        delta: object = choice.get("delta")
        content: str = (
            self._content(delta.get("content")) if isinstance(delta, dict) else ""
        )
        chunk: ChatStreamChunk = self._chunk(
            content,
            self._finish_reason(choice.get("finish_reason")),
            self._usage(payload.get("usage")),
            model,
        )
        if not chunk.content and chunk.finish_reason is None:
            return None
        return chunk


class MistralProvider(OpenAIProvider):
    name = "mistral"
    default_base_url = "https://api.mistral.ai/v1"


class HetznerProvider(OpenAIProvider):
    name = "hetzner"
    default_base_url = "https://inference.hetzner.com/api/v1"
    default_max_tokens = 4096


class AzureOpenAIProvider(OpenAIProvider):
    name = "azure_openai"
    default_base_url = ""

    def completions_url(self, model: str) -> str:
        version: str = str(self.config.options.get("api_version", "2024-10-21"))
        return (
            f"{self._base_url(self.default_base_url)}/openai/deployments/{_model_path(model)}"
            f"/chat/completions?api-version={version}"
        )

    def _request_payload(self, request: ChatRequest, model: str) -> dict[str, object]:
        payload: dict[str, object] = super()._request_payload(request, model)
        payload.pop("model", None)
        payload.pop("api_version", None)
        return payload

    def completion_headers(self) -> dict[str, str]:
        if self.config.api_key is None:
            return {}
        return {"api-key": self.config.api_key.get_secret_value()}

    async def list_models(self) -> list[str]:
        return [self.config.default_model] if self.config.default_model else []


class AnthropicProvider(HTTPProvider):
    name = "anthropic"
    default_base_url = "https://api.anthropic.com/v1"

    def completions_url(self, model: str) -> str:
        del model
        return f"{self._base_url(self.default_base_url)}/messages"

    def completion_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"anthropic-version": "2023-06-01"}
        if self.config.api_key is not None:
            headers["x-api-key"] = self.config.api_key.get_secret_value()
        return headers

    def _request_payload(self, request: ChatRequest, model: str) -> dict[str, object]:
        messages: list[dict[str, str]] = []
        system: list[str] = []
        for message in request.messages:
            if message.role == "system":
                system.append(message.content)
            else:
                role: str = "assistant" if message.role == "assistant" else "user"
                if messages and messages[-1]["role"] == role:
                    messages[-1]["content"] += f"\n\n{message.content}"
                else:
                    messages.append({"role": role, "content": message.content})
        payload: dict[str, object] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "stream": False,
            **self._options(),
        }
        if system:
            payload["system"] = "\n\n".join(system)
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.response_format == "json_object":
            payload["output_config"] = {"format": {"type": "json"}}
        return payload

    def _normalized_response(
        self, data: dict[str, object], request: ChatRequest, model: str
    ) -> ChatResponse:
        del request
        return ChatResponse(
            provider=self.name,
            model=model,
            content=self._content(data.get("content")),
            finish_reason=self._finish_reason(data.get("stop_reason")),
            usage=self._usage(data.get("usage")),
            request_id=self._string(data.get("id")) or uuid4().hex,
        )

    async def list_models(self) -> list[str]:
        data: dict[str, object] = self._json(
            await self._get(
                f"{self._base_url(self.default_base_url)}/models",
                self.completion_headers(),
                {"limit": "100"},
            )
        )
        models: object = data.get("data")
        return (
            sorted(
                item["id"]
                for item in models
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            )
            if isinstance(models, list)
            else []
        )

    def _parse_stream_line(
        self, line: str, request: ChatRequest, model: str
    ) -> ChatStreamChunk | None:
        if not line.startswith("data:"):
            return None
        data: str = line[5:].strip()
        if data == "[DONE]":
            return None
        try:
            payload: object = json.loads(data)
        except json.JSONDecodeError as exc:
            raise StreamingInterruptedError() from exc
        if not isinstance(payload, dict):
            return None
        event_type: str | None = self._string(payload.get("type"))
        if event_type == "content_block_delta":
            delta: object = payload.get("delta")
            if isinstance(delta, dict):
                return self._chunk(self._string(delta.get("text")) or "", model=model)
        if event_type == "message_delta":
            delta = payload.get("delta")
            return self._chunk(
                finish_reason=self._finish_reason(delta.get("stop_reason"))
                if isinstance(delta, dict)
                else None,
                usage=self._usage(payload.get("usage")),
                model=model,
            )
        if event_type == "message_start":
            message: object = payload.get("message")
            return self._chunk(
                usage=self._usage(message.get("usage"))
                if isinstance(message, dict)
                else None,
                model=model,
            )
        return None

    def _parse_stream_data(
        self, data: str, request: ChatRequest, model: str
    ) -> ChatStreamChunk | None:
        return self._parse_stream_line(f"data: {data}", request, model)


class GoogleProvider(HTTPProvider):
    name = "google"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"

    def _url(self, model: str, action: str) -> str:
        return (
            f"{self._base_url(self.default_base_url)}/models/"
            f"{_model_path(model)}:{action}"
        )

    def completions_url(self, model: str) -> str:
        del model
        raise NotImplementedError

    def _request_payload(self, request: ChatRequest, model: str) -> dict[str, object]:
        del model
        contents: list[dict[str, object]] = []
        system: list[str] = []
        for message in request.messages:
            if message.role == "system":
                system.append(message.content)
            else:
                contents.append(
                    {
                        "role": "model" if message.role == "assistant" else "user",
                        "parts": [{"text": message.content}],
                    }
                )
        generation: dict[str, object] = {
            "maxOutputTokens": request.max_tokens,
            **self._options(
                frozenset(
                    {
                        "model",
                        "messages",
                        "stream",
                        "temperature",
                        "max_tokens",
                        "top_p",
                        "response_format",
                    }
                )
            ),
        }
        if request.temperature is not None:
            generation["temperature"] = request.temperature
        if request.top_p is not None:
            generation["topP"] = request.top_p
        if request.response_format == "json_object":
            generation["responseMimeType"] = "application/json"
        payload: dict[str, object] = {
            "contents": contents,
            "generationConfig": generation,
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system)}]}
        return payload

    def completion_headers(self) -> dict[str, str]:
        return {}

    async def complete(self, request: ChatRequest, model: str) -> ChatResponse:
        response: httpx2.Response = await self._post(
            self._url(model, "generateContent"),
            request,
            model,
            params=self._api_key_params(),
        )
        return self._normalized_response(self._json(response), request, model)

    def _api_key_params(self) -> dict[str, str]:
        if self.config.api_key is None:
            return {}
        return {"key": self.config.api_key.get_secret_value()}

    def _normalized_response(
        self, data: dict[str, object], request: ChatRequest, model: str
    ) -> ChatResponse:
        del request
        candidates: object = data.get("candidates")
        candidate: object = (
            candidates[0] if isinstance(candidates, list) and candidates else None
        )
        content: object = (
            candidate.get("content") if isinstance(candidate, dict) else None
        )
        parts: object = content.get("parts") if isinstance(content, dict) else None
        return ChatResponse(
            provider=self.name,
            model=model,
            content=self._content(parts),
            finish_reason=self._finish_reason(candidate.get("finishReason"))
            if isinstance(candidate, dict)
            else None,
            usage=self._google_usage(data.get("usageMetadata")),
            request_id=uuid4().hex,
        )

    @staticmethod
    def _google_usage(value: object) -> TokenUsage | None:
        if not isinstance(value, dict):
            return None
        prompt: object = value.get("promptTokenCount")
        completion: object = value.get("candidatesTokenCount")
        total: object = value.get("totalTokenCount")
        return TokenUsage(
            prompt_tokens=prompt if isinstance(prompt, int) else None,
            completion_tokens=completion if isinstance(completion, int) else None,
            total_tokens=total if isinstance(total, int) else None,
        )

    async def list_models(self) -> list[str]:
        response: httpx2.Response = await self._get(
            f"{self._base_url(self.default_base_url)}/models",
            params=self._api_key_params(),
        )
        data: dict[str, object] = self._json(response)
        models: object = data.get("models")
        return (
            sorted(
                item["name"].removeprefix("models/")
                for item in models
                if isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and _supports_google_generate(item)
            )
            if isinstance(models, list)
            else []
        )

    def _parse_stream_data(
        self, data: str, request: ChatRequest, model: str
    ) -> ChatStreamChunk | None:
        try:
            payload: object = json.loads(data)
        except json.JSONDecodeError as exc:
            raise StreamingInterruptedError() from exc
        if not isinstance(payload, dict):
            return None
        candidates: object = payload.get("candidates")
        candidate: object = (
            candidates[0] if isinstance(candidates, list) and candidates else None
        )
        content: object = (
            candidate.get("content") if isinstance(candidate, dict) else None
        )
        parts: object = content.get("parts") if isinstance(content, dict) else None
        return self._chunk(
            self._content(parts),
            self._finish_reason(candidate.get("finishReason"))
            if isinstance(candidate, dict)
            else None,
            self._google_usage(payload.get("usageMetadata")),
            model,
        )

    async def _stream(
        self, request: ChatRequest, model: str
    ) -> AsyncGenerator[ChatStreamChunk]:
        response_received: bool = False
        try:
            async with self.client.stream(
                "POST",
                self._url(model, "streamGenerateContent"),
                json=self._request_payload(request, model),
                headers=self.completion_headers(),
                params={"alt": "sse", **self._api_key_params()},
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


class OllamaProvider(HTTPProvider):
    name = "ollama"
    default_base_url = "http://localhost:11434"

    def completions_url(self, model: str) -> str:
        del model
        return f"{self._base_url(self.default_base_url)}/api/chat"

    def _request_payload(self, request: ChatRequest, model: str) -> dict[str, object]:
        options: dict[str, str | int | float | bool] = {
            **self._options(),
            "num_predict": request.max_tokens,
        }
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.top_p is not None:
            options["top_p"] = request.top_p
        payload: dict[str, object] = {
            "model": model,
            "messages": [message.model_dump() for message in request.messages],
            "stream": False,
            "options": options,
        }
        if request.response_format == "json_object":
            payload["format"] = "json"
        return payload

    def _normalized_response(
        self, data: dict[str, object], request: ChatRequest, model: str
    ) -> ChatResponse:
        del request
        message: object = data.get("message")
        return ChatResponse(
            provider=self.name,
            model=model,
            content=self._content(message.get("content"))
            if isinstance(message, dict)
            else "",
            finish_reason=self._finish_reason(data.get("done_reason")),
            usage=TokenUsage(
                prompt_tokens=_optional_int(data.get("prompt_eval_count")),
                completion_tokens=_optional_int(data.get("eval_count")),
                total_tokens=_sum_token_counts(
                    data.get("prompt_eval_count"), data.get("eval_count")
                ),
            ),
            request_id=uuid4().hex,
        )

    async def list_models(self) -> list[str]:
        data: dict[str, object] = self._json(
            await self._get(f"{self._base_url(self.default_base_url)}/api/tags")
        )
        models: object = data.get("models")
        return (
            sorted(
                item["name"]
                for item in models
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            )
            if isinstance(models, list)
            else []
        )

    def _parse_stream_line(
        self, line: str, request: ChatRequest, model: str
    ) -> ChatStreamChunk | None:
        del request
        if not line:
            return None
        try:
            payload: object = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StreamingInterruptedError() from exc
        if not isinstance(payload, dict):
            return None
        message: object = payload.get("message")
        return self._chunk(
            self._content(message.get("content")) if isinstance(message, dict) else "",
            self._finish_reason(payload.get("done_reason")),
            TokenUsage(
                prompt_tokens=_optional_int(payload.get("prompt_eval_count")),
                completion_tokens=_optional_int(payload.get("eval_count")),
                total_tokens=_sum_token_counts(
                    payload.get("prompt_eval_count"), payload.get("eval_count")
                ),
            )
            if payload.get("done") is True
            else None,
            model,
        )

    def _parse_stream_data(
        self, data: str, request: ChatRequest, model: str
    ) -> ChatStreamChunk | None:
        return self._parse_stream_line(data, request, model)


def _sum_token_counts(prompt: object, completion: object) -> int | None:
    if isinstance(prompt, int) and isinstance(completion, int):
        return prompt + completion
    return None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _model_path(model: str) -> str:
    return quote(model.removeprefix("models/"), safe="")


def _supports_google_generate(model: dict[str, object]) -> bool:
    methods: object = model.get("supportedGenerationMethods")
    return isinstance(methods, list) and "generateContent" in methods
