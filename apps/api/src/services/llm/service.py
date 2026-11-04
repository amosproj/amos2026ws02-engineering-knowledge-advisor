from collections.abc import AsyncGenerator

import httpx2

from config.settings import LLMProviderSettings, Settings
from services.llm.errors import (
    InvalidLLMRequestError,
    InvalidProviderError,
    ProviderDisabledError,
)
from services.llm.models import (
    ChatRequest,
    ChatResponse,
    ChatStreamChunk,
    ModelInfo,
    ProviderInfo,
)
from services.llm.providers import (
    AnthropicProvider,
    AzureOpenAIProvider,
    GoogleProvider,
    HetznerProvider,
    HTTPProvider,
    LLMProvider,
    MistralProvider,
    OllamaProvider,
    OpenAIProvider,
)

_PROVIDER_TYPES: dict[str, type[HTTPProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "mistral": MistralProvider,
    "ollama": OllamaProvider,
    "azure_openai": AzureOpenAIProvider,
    "hetzner": HetznerProvider,
}


class LLMService:
    def __init__(
        self,
        settings: Settings,
        client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx2.AsyncClient()
        configs: dict[str, LLMProviderSettings] = settings.llm_provider_settings()
        self._providers: dict[str, LLMProvider] = {
            name: _PROVIDER_TYPES[name](config, self._client)
            for name, config in configs.items()
            if config.enabled
        }

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def list_providers(self) -> list[ProviderInfo]:
        configs: dict[str, LLMProviderSettings] = self._settings.llm_provider_settings()
        return [
            ProviderInfo(name=name, default_model=configs[name].default_model)
            for name in self._providers
        ]

    async def list_models(self, provider: str | None = None) -> list[ModelInfo]:
        if provider is not None:
            configured: LLMProvider = self._get_provider(provider)
            return [
                ModelInfo(provider=provider, model=model)
                for model in await configured.list_models()
            ]

        configs: dict[str, LLMProviderSettings] = self._settings.llm_provider_settings()
        return [
            ModelInfo(provider=name, model=config.default_model)
            for name, config in configs.items()
            if name in self._providers and config.default_model is not None
        ]

    async def complete(self, request: ChatRequest) -> ChatResponse:
        provider_name: str = self._resolve_provider_name(request.provider)
        provider: LLMProvider = self._get_provider(provider_name)
        model: str = self._resolve_model(request.model, provider_name)
        return await provider.complete(request, model)

    def stream(self, request: ChatRequest) -> AsyncGenerator[ChatStreamChunk]:
        provider_name: str = self._resolve_provider_name(request.provider)
        provider: LLMProvider = self._get_provider(provider_name)
        model: str = self._resolve_model(request.model, provider_name)
        return provider.stream(request, model)

    def _resolve_provider_name(self, requested: str | None) -> str:
        provider: str | None = requested or self._settings.llm_default_provider
        if provider is None:
            raise InvalidLLMRequestError(
                "A provider must be selected or configured as the default."
            )
        if provider not in _PROVIDER_TYPES:
            raise InvalidProviderError()
        return provider

    def _get_provider(self, name: str) -> LLMProvider:
        provider: LLMProvider | None = self._providers.get(name)
        if provider is None:
            if name not in _PROVIDER_TYPES:
                raise InvalidProviderError()
            raise ProviderDisabledError()
        return provider

    def _resolve_model(self, requested: str | None, provider: str) -> str:
        if requested is not None:
            return requested
        model: str | None = self._settings.llm_provider_settings()[
            provider
        ].default_model
        if model is None:
            raise InvalidLLMRequestError(
                "A model must be selected or configured as the provider default."
            )
        return model
