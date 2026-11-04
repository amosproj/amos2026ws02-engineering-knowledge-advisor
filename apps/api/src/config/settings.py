from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    profile: Literal["dev", "prod"] = "dev"

    database_url: SecretStr | None = None

    ograg_ontology_path: Path  # required field

    s3_endpoint_url: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: SecretStr
    s3_region: str
    # where the browser reaches the storage, e.g. through the /storage proxy
    s3_public_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
