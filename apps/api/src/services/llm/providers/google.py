import json
from collections.abc import AsyncGenerator
from uuid import uuid4

import httpx2

from services.llm.errors import (
    ProviderTimeoutError,
    ProviderUnavailableError,
    StreamingInterruptedError,
)
from services.llm.models import ChatRequest, ChatResponse, ChatStreamChunk, TokenUsage
from services.llm.providers.base import HTTPProvider
from services.llm.providers.utils import model_path, supports_google_generate


class GoogleProvider(HTTPProvider):
    name = "google"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"

    def _url(self, model: str, action: str) -> str:
        return (
            f"{self._base_url(self.default_base_url)}/models/"
            f"{model_path(model)}:{action}"
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
                and supports_google_generate(item)
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
