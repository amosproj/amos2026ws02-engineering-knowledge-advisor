from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from services.llm.models import (
        ChatRequest,
        ChatResponse,
        ChatStreamChunk,
        ModelInfo,
        ProviderInfo,
    )


class LLMService(Protocol):
    """Inference service for configured LLM providers."""

    @abstractmethod
    async def close(self) -> None:
        """Releases the HTTP client if the service created it."""
        ...

    @abstractmethod
    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Returns the whole answer. Uses the default provider and model when the ``request`` names none."""
        ...

    @abstractmethod
    def stream(self, request: ChatRequest) -> AsyncGenerator[ChatStreamChunk]:
        """Yields the answer in chunks as the provider sends them."""
        ...

    @abstractmethod
    def list_providers(self) -> list[ProviderInfo]:
        """Returns the enabled providers with their default models."""
        ...

    @abstractmethod
    async def list_models(self, provider: str | None = None) -> list[ModelInfo]:
        """Returns the provider's models, or the default model of each enabled provider when ``provider`` is None."""
        ...
