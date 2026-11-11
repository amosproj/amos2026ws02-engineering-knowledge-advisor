from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderSettings(BaseModel):
    enabled: bool = False
    api_key: SecretStr | None = None
    base_url: str | None = None
    default_model: str | None = None
    timeout_seconds: float = Field(default=60, gt=0, le=600)
    options: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("api_key", "base_url", "default_model", mode="before")
    @classmethod
    def empty_string_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, str):
            return value.strip()
        return value


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

    profile: Literal["dev", "prod"] = "dev"
    database_url: SecretStr | None = None

    ograg_ontology_path: Path

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
                raise ValueError("llm_default_provider is not supported")
            if not providers[self.llm_default_provider].enabled:
                raise ValueError("llm_default_provider must be enabled")

        for name, config in providers.items():
            if (
                config.enabled
                and name != "ollama"
                and (
                    config.api_key is None
                    or not config.api_key.get_secret_value().strip()
                )
            ):
                raise ValueError(f"API key is required for enabled provider {name}")
            if config.enabled and name == "azure_openai" and not config.base_url:
                raise ValueError(
                    "base_url is required for enabled provider azure_openai"
                )
        return self

    def llm_provider_settings(self) -> dict[str, LLMProviderSettings]:
        return {
            "openai": self.llm_openai,
            "anthropic": self.llm_anthropic,
            "google": self.llm_google,
            "mistral": self.llm_mistral,
            "ollama": self.llm_ollama,
            "azure_openai": self.llm_azure_openai,
            "hetzner": self.llm_hetzner,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
