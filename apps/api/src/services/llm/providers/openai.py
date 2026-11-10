import json
from uuid import uuid4

from services.llm.errors import ProviderUnavailableError, StreamingInterruptedError
from services.llm.models import ChatRequest, ChatResponse, ChatStreamChunk
from services.llm.providers.base import HTTPProvider


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
