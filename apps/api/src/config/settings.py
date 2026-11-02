from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
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
    database_url: SecretStr = Field(validation_alias="DATABASE_URL")
    s3_endpoint_url: str = Field(validation_alias="S3_ENDPOINT_URL")
    s3_bucket: str = Field(validation_alias="S3_BUCKET")
    s3_access_key: str = Field(validation_alias="S3_ACCESS_KEY")
    s3_secret_key: SecretStr = Field(validation_alias="S3_SECRET_KEY")
    s3_region: str = Field(validation_alias="S3_REGION")


@lru_cache
def get_settings() -> Settings:
    return Settings()
