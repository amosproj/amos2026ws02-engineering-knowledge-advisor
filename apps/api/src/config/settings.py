from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    profile: Literal["dev", "prod"] = "dev"

    database_url: SecretStr | None = None

    ograg_ontology_path: Path  # required field
    ograg_embed_dim: int = Field(default=384, gt=0)  # BAAI/bge-small-en-v1.5


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
