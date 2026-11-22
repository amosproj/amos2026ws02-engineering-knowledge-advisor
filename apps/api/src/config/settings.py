from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# TODO: env var for embedding model
# intfloat/multilingual-e5-base
DEFAULT_EMBEDDING_DIMENSIONS: int = 768

DEFAULT_SEARCH_TOP_K: int = 10
DEFAULT_SEARCH_MAX_EDGES: int = 8
DEFAULT_SEARCH_CANDIDATE_POOL: int = 50
DEFAULT_SEARCH_MIN_SIMILARITY: float = 0.72  # depends on the embedding model
DEFAULT_SEARCH_LEXICAL_MIN_SIMILARITY: float = 0.6

type Profile = Literal["dev", "prod"]
DEFAULT_PROFILE: Profile = "dev"

DEFAULT_LLM_TIMEOUT_SECONDS: float = 60
MAX_LLM_TIMEOUT_SECONDS: float = 600

ERROR_POOL_SMALLER_THAN_TOP_K: str = (
    "candidate_pool ({candidate_pool}) must be >= ({top_k})"
)
ERROR_DEFAULT_PROVIDER_UNSUPPORTED: str = "llm_default_provider is not supported"
ERROR_DEFAULT_PROVIDER_DISABLED: str = "llm_default_provider must be enabled"
ERROR_API_KEY_REQUIRED: str = "API key is required for enabled provider {provider_name}"
ERROR_BASE_URL_REQUIRED: str = (
    "base_url is required for enabled provider {provider_name}"
)


class LLMProviderName(StrEnum):
    """LLM providers that can be configured with ``API_LLM_<PROVIDER>__*``."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    MISTRAL = "mistral"
    OLLAMA = "ollama"
    AZURE_OPENAI = "azure_openai"
    HETZNER = "hetzner"


class LLMProviderSettings(BaseModel):
    enabled: bool = False
    api_key: SecretStr | None = None
    base_url: str | None = None
    default_model: str | None = None
    timeout_seconds: float = Field(
        default=DEFAULT_LLM_TIMEOUT_SECONDS, gt=0, le=MAX_LLM_TIMEOUT_SECONDS
    )
    options: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("api_key", "base_url", "default_model", mode="before")
    @classmethod
    def empty_string_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, str):
            return value.strip()
        return value


class SearchSettings(BaseModel):
    """Knowledge search settings that can be configured with ``API_SEARCH__*``.

    Attributes:
        top_k: count of hypernodes taken by value and by key similarity per search request (``k``).
               ``top_k`` closest in meaning for hypernode value from the ``candidate_pool`` + up to ``top_k`` closest in meaning for hypernode key from separate search.
        max_edges: count of facts (hyperedges) given to the LLM as context (``L``).
        candidate_pool: count of value embedding hits fetched from the vector store per search request, at least ``top_k``.

        min_similarity: ``Gate 1``: a search request is refused if no hypernode passes this similarity threshold, and no lexical value passes ``lexical_min_similarity``.
                        Depends on the embedding model.
        lexical_min_similarity: opens ``Gate 1`` if value of a ``lexical`` property passes this threshold, and makes the passing hypernode a candidate to be selected as context.
    """

    top_k: int = Field(default=DEFAULT_SEARCH_TOP_K, gt=0)
    max_edges: int = Field(default=DEFAULT_SEARCH_MAX_EDGES, gt=0)
    candidate_pool: int = Field(default=DEFAULT_SEARCH_CANDIDATE_POOL, gt=0)
    min_similarity: float = Field(default=DEFAULT_SEARCH_MIN_SIMILARITY, ge=0, le=1)
    lexical_min_similarity: float = Field(
        default=DEFAULT_SEARCH_LEXICAL_MIN_SIMILARITY, ge=0, le=1
    )

    @model_validator(mode="after")
    def validate_candidate_pool(self) -> SearchSettings:
        """Checks that the top ``k`` can be taken from the candidate pool."""
        if self.candidate_pool < self.top_k:
            raise ValueError(
                ERROR_POOL_SMALLER_THAN_TOP_K.format(
                    candidate_pool=self.candidate_pool, top_k=self.top_k
                )
            )
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="API_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_ignore_empty=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    # fields without a default value are required

    profile: Profile = DEFAULT_PROFILE
    database_url: SecretStr | None = None

    ontology_path: Path
    embedding_dimensions: int = Field(default=DEFAULT_EMBEDDING_DIMENSIONS, gt=0)
    search: SearchSettings = Field(default_factory=SearchSettings)

    s3_endpoint_url: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: SecretStr
    s3_region: str
    # where the browser reaches the storage, e.g. through the /storage proxy
    s3_public_url: str

    llm_default_provider: str | None = None
    llm_openai: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    llm_anthropic: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    llm_google: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    llm_mistral: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    llm_ollama: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    llm_azure_openai: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    llm_hetzner: LLMProviderSettings = Field(default_factory=LLMProviderSettings)

    @model_validator(mode="after")
    def validate_llm_configuration(self) -> Settings:
        providers: dict[str, LLMProviderSettings] = self.llm_provider_settings()
        if self.llm_default_provider is not None:
            if self.llm_default_provider not in providers:
                raise ValueError(ERROR_DEFAULT_PROVIDER_UNSUPPORTED)
            if not providers[self.llm_default_provider].enabled:
                raise ValueError(ERROR_DEFAULT_PROVIDER_DISABLED)

        for name, config in providers.items():
            if (
                config.enabled
                and name != LLMProviderName.OLLAMA
                and (
                    config.api_key is None
                    or not config.api_key.get_secret_value().strip()
                )
            ):
                raise ValueError(ERROR_API_KEY_REQUIRED.format(provider_name=name))
            if (
                config.enabled
                and name == LLMProviderName.AZURE_OPENAI
                and not config.base_url
            ):
                raise ValueError(ERROR_BASE_URL_REQUIRED.format(provider_name=name))
        return self

    def llm_provider_settings(self) -> dict[str, LLMProviderSettings]:
        return {
            LLMProviderName.OPENAI: self.llm_openai,
            LLMProviderName.ANTHROPIC: self.llm_anthropic,
            LLMProviderName.GOOGLE: self.llm_google,
            LLMProviderName.MISTRAL: self.llm_mistral,
            LLMProviderName.OLLAMA: self.llm_ollama,
            LLMProviderName.AZURE_OPENAI: self.llm_azure_openai,
            LLMProviderName.HETZNER: self.llm_hetzner,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
