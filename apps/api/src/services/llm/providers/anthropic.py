import json
from uuid import uuid4

from services.llm.constants import STREAM_DONE
from services.llm.errors import StreamingInterruptedError
from services.llm.models import ChatRequest, ChatResponse, ChatStreamChunk
from services.llm.providers.base import HTTPProvider


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
        if data == STREAM_DONE:
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
