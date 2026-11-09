import json
from uuid import uuid4

from services.llm.errors import StreamingInterruptedError
from services.llm.models import ChatRequest, ChatResponse, ChatStreamChunk, TokenUsage
from services.llm.providers.base import HTTPProvider
from services.llm.providers.utils import optional_int, sum_token_counts


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
                prompt_tokens=optional_int(data.get("prompt_eval_count")),
                completion_tokens=optional_int(data.get("eval_count")),
                total_tokens=sum_token_counts(
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
                prompt_tokens=optional_int(payload.get("prompt_eval_count")),
                completion_tokens=optional_int(payload.get("eval_count")),
                total_tokens=sum_token_counts(
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
