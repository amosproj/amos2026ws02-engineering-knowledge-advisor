from pathlib import Path

import pytest
from pydantic import ValidationError

from config import Settings, get_settings


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("API_PROFILE", raising=False)
    return tmp_path


def test_settings_env(isolated: Path):
    env: Path = isolated / ".env"
    env.write_text("API_PROFILE=prod")
    assert Settings().profile == "prod"


def test_settings_reject_unknowns(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_PROFILE", "thisprofiledoesnotexist")
    with pytest.raises(ValidationError):
        Settings()


def test_settings_cache(monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()

    monkeypatch.setenv("API_PROFILE", "dev")
    first: Settings = get_settings()

    monkeypatch.setenv("API_PROFILE", "prod")
    assert get_settings() is first

    get_settings.cache_clear()
    assert get_settings().profile == "prod"

    get_settings.cache_clear()  # cleanup
