from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from services.llm_impl.models import (
        ChatRequest,
        ChatResponse,
        ChatStreamChunk,
        ModelInfo,
        ProviderInfo,
    )


class LLMService(Protocol):
    async def close(self) -> None: ...

    async def complete(self, request: ChatRequest) -> ChatResponse: ...

    def stream(self, request: ChatRequest) -> AsyncGenerator[ChatStreamChunk]: ...

    def list_providers(self) -> list[ProviderInfo]: ...

    async def list_models(self, provider: str | None = None) -> list[ModelInfo]: ...
