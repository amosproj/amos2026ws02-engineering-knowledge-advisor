from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from pydantic import SecretStr

import services.s3.storage as s3_storage
from config.settings import Settings
from services.object_storage import ObjectStorageError, StoredObject
from services.s3 import S3ObjectStorage


def client_error(status: int) -> ClientError:
    response: Any = {
        "Error": {"Code": str(status)},
        "ResponseMetadata": {"HTTPStatusCode": status},
    }
    return ClientError(
        response,
        "operation",
    )


@pytest.fixture
def client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def storage(client: MagicMock, monkeypatch: pytest.MonkeyPatch) -> S3ObjectStorage:
    storage = S3ObjectStorage(
        Settings(
            ograg_ontology_path=Path("ontology.jsonld"),
            s3_endpoint_url="http://localhost:9000",
            s3_bucket="bucket",
            s3_access_key="key",
            s3_secret_key=SecretStr("secret"),
            s3_region="us-east-1",
            s3_public_url="/storage/",
        )
    )
    monkeypatch.setattr(storage, "_client", client)
    monkeypatch.setattr(s3_storage.time, "sleep", lambda _: None)
    return storage


def test_a_missing_object_is_none_and_a_failure_an_object_storage_error(
    storage: S3ObjectStorage, client: MagicMock
):
    client.head_object.side_effect = client_error(404)
    assert storage.get_object_size("k") is None
    client.get_object.side_effect = client_error(404)
    assert storage.read_object("k", 10) is None

    client.head_object.side_effect = client_error(500)
    with pytest.raises(ObjectStorageError):
        storage.get_object_size("k")


def test_reading_closes_the_object_also_when_stopped_early_or_failing(
    storage: S3ObjectStorage, client: MagicMock
):
    body = MagicMock()
    body.iter_chunks.return_value = iter([b"a", b"b"])
    client.get_object.return_value = {"Body": body}
    chunks = storage.read_object("k", 10)
    assert chunks is not None
    assert next(chunks) == b"a"
    chunks.close()
    body.close.assert_called_once()

    body = MagicMock()
    client.get_object.return_value = {"Body": body}
    chunks = storage.read_object("k", 10)
    assert chunks is not None
    chunks.close()
    body.close.assert_called_once()

    def failing() -> Iterator[bytes]:
        yield b"a"
        raise EndpointConnectionError(endpoint_url="http://localhost:9000")

    body = MagicMock()
    body.iter_chunks.return_value = failing()
    client.get_object.return_value = {"Body": body}
    chunks = storage.read_object("k", 10)
    assert chunks is not None
    with pytest.raises(ObjectStorageError):
        list(chunks)
    body.close.assert_called_once()


def test_a_failing_listing_page_is_an_object_storage_error(
    storage: S3ObjectStorage, client: MagicMock
):
    modified = datetime(2026, 11, 1, tzinfo=UTC)

    def pages() -> Iterator[dict[str, object]]:
        yield {"Contents": [{"Key": "a", "LastModified": modified}]}
        raise client_error(503)

    client.get_paginator.return_value.paginate.return_value = pages()
    listing = storage.list_objects("machines/")

    assert next(listing) == [StoredObject("a", modified)]
    with pytest.raises(ObjectStorageError):
        next(listing)


def test_deleting_folders_logs_failures_instead_of_raising(
    storage: S3ObjectStorage, client: MagicMock
):
    client.get_paginator.return_value.paginate.side_effect = client_error(500)
    storage.delete_folders_quietly(["machines/m/"])


def test_the_bucket_check_retries_until_the_storage_answers(
    storage: S3ObjectStorage, client: MagicMock
):
    client.head_bucket.side_effect = [
        EndpointConnectionError(endpoint_url="http://localhost:9000"),
        client_error(503),
        client_error(404),
    ]
    storage.ensure_bucket()
    client.create_bucket.assert_called_once_with(Bucket="bucket")

    client.head_bucket.side_effect = client_error(403)
    with pytest.raises(ObjectStorageError):
        storage.ensure_bucket()
    assert client.head_bucket.call_count == 4


def test_the_upload_form_points_to_the_public_url(
    storage: S3ObjectStorage, client: MagicMock
):
    client.generate_presigned_post.return_value = {"url": "x", "fields": {"key": "k"}}
    assert storage.create_upload_form("k", 3) == ("/storage/bucket", {"key": "k"})
    conditions = client.generate_presigned_post.call_args.kwargs["Conditions"]
    assert ["content-length-range", 3, 3] in conditions
