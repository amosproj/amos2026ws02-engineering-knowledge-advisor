import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test"
)
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("S3_BUCKET", "test")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")
os.environ.setdefault("S3_REGION", "us-east-1")
os.environ.setdefault("S3_PUBLIC_URL", "/storage")


@pytest.fixture
def app():
    from main import app

    return app


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c
