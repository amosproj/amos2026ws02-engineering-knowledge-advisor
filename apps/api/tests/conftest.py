from collections.abc import Iterator

import pytest
from fakes import ONTOLOGY_PATH
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.settings import get_settings

# route tests need a database URL, but not a whole database
TEST_DATABASE_URL: str = "postgresql+psycopg://test@localhost:5432/test"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    from main import app

    monkeypatch.setenv("API_DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("API_OGRAG_ONTOLOGY_PATH", str(ONTOLOGY_PATH))
    get_settings.cache_clear()
    yield app
    get_settings.cache_clear()  # clear for next test


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client
