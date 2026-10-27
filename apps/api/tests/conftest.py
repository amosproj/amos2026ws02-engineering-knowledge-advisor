import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from main import app

    return app


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c
