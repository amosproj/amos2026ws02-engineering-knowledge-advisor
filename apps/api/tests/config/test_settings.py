from pathlib import Path

import pytest
from helpers import S3_ENV
from pydantic import ValidationError

from config.settings import Settings, get_settings

ONTOLOGY_PATH: str = "ontology.jsonld"


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("API_PROFILE", raising=False)
    monkeypatch.setenv("API_OGRAG_ONTOLOGY_PATH", ONTOLOGY_PATH)
    for name, value in S3_ENV.items():
        monkeypatch.setenv(name, value)
    return tmp_path


def test_settings_env(isolated: Path):
    env: Path = isolated / ".env"
    env.write_text("API_PROFILE=prod")
    assert Settings().profile == "prod"  # pyright: ignore[reportCallIssue]


def test_settings_reject_unknowns(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_PROFILE", "thisprofiledoesnotexist")
    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize("name", S3_ENV)
def test_settings_require_s3(monkeypatch: pytest.MonkeyPatch, name: str):
    monkeypatch.delenv(name)
    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue]


def test_settings_cache(monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()

    monkeypatch.setenv("API_PROFILE", "dev")
    first: Settings = get_settings()

    monkeypatch.setenv("API_PROFILE", "prod")
    assert get_settings() is first

    get_settings.cache_clear()
    assert get_settings().profile == "prod"

    get_settings.cache_clear()  # cleanup


def test_llm_provider_configuration_uses_nested_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("API_LLM_OPENAI__ENABLED", "true")
    monkeypatch.setenv("API_LLM_OPENAI__API_KEY", "test-secret")
    monkeypatch.setenv("API_LLM_OPENAI__DEFAULT_MODEL", "test-model")
    monkeypatch.setenv("API_LLM_DEFAULT_PROVIDER", "openai")

    settings = Settings()  # pyright: ignore[reportCallIssue]

    assert settings.llm_openai.enabled
    assert settings.llm_openai.api_key is not None
    assert settings.llm_openai.api_key.get_secret_value() == "test-secret"
    assert settings.llm_openai.default_model == "test-model"
    assert settings.llm_default_provider == "openai"


def test_hetzner_configuration_uses_nested_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("API_LLM_HETZNER__ENABLED", "true")
    monkeypatch.setenv("API_LLM_HETZNER__API_KEY", "hetzner-test-secret")
    monkeypatch.setenv("API_LLM_HETZNER__DEFAULT_MODEL", "test-model")

    settings = Settings()  # pyright: ignore[reportCallIssue]

    assert settings.llm_hetzner.enabled
    assert settings.llm_hetzner.api_key is not None
    assert settings.llm_hetzner.api_key.get_secret_value() == "hetzner-test-secret"
    assert settings.llm_hetzner.default_model == "test-model"


def test_enabled_remote_llm_provider_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("API_LLM_OPENAI__ENABLED", "true")
    monkeypatch.delenv("API_LLM_OPENAI__API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue]


def test_empty_optional_llm_environment_values_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("API_LLM_DEFAULT_PROVIDER", "")
    monkeypatch.setenv("API_LLM_OPENAI__API_KEY", "")
    monkeypatch.setenv("API_LLM_OPENAI__BASE_URL", "")
    monkeypatch.setenv("API_LLM_OPENAI__DEFAULT_MODEL", "")

    settings = Settings()  # pyright: ignore[reportCallIssue]

    assert settings.llm_default_provider is None
    assert settings.llm_openai.api_key is None
    assert settings.llm_openai.base_url is None
    assert settings.llm_openai.default_model is None
