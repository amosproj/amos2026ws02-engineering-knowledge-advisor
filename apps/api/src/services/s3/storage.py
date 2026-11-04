import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectionError,
    HTTPClientError,
)
from botocore.response import StreamingBody

from config.settings import Settings
from logger import logger
from services.object_storage import ObjectStorage, ObjectStorageError, StoredObject

if TYPE_CHECKING:  # the stubs are a dev dependency
    from types_boto3_s3 import S3Client
    from types_boto3_s3.paginator import ListObjectsV2Paginator
    from types_boto3_s3.type_defs import (
        DeleteObjectsOutputTypeDef,
        GetObjectOutputTypeDef,
        HeadObjectOutputTypeDef,
    )

BUCKET_CHECK_ATTEMPTS = 30
BUCKET_CHECK_DELAY_SECONDS = 2
UPLOAD_FORM_EXPIRES_SECONDS = 3600
UPLOAD_CONTENT_TYPE = "application/octet-stream"
DELETE_BATCH_SIZE = 1000


@contextmanager
def _storage_errors() -> Iterator[None]:
    try:
        yield
    except (BotoCoreError, ClientError) as error:
        raise ObjectStorageError(str(error)) from error


def _http_status(error: ClientError) -> int:
    return error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)


class S3ObjectStorage(ObjectStorage):
    """Object storage on S3 (MinIO in Docker)."""

    def __init__(self, settings: Settings) -> None:
        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            region_name=settings.s3_region,
            config=Config(
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 0},
                s3={"addressing_style": "path"},
            ),
        )
        self._bucket: str = settings.s3_bucket
        # The browser reaches the storage through a same-origin proxy, not the internal endpoint
        self._public_url: str = f"{settings.s3_public_url.rstrip('/')}/{self._bucket}"

    def ensure_bucket(self) -> None:
        last_error: Exception | None = None
        for _ in range(BUCKET_CHECK_ATTEMPTS):
            try:
                if self._bucket_exists():
                    logger.info(f"Bucket {self._bucket} already exists")
                else:
                    self._client.create_bucket(Bucket=self._bucket)
                    logger.info(f"Created bucket {self._bucket}")
                return
            except ClientError as error:
                if _http_status(error) < 500:
                    raise ObjectStorageError(str(error)) from error
                last_error = error
            except (ConnectionError, HTTPClientError) as error:
                last_error = error

            logger.info("Object storage is not ready yet, retrying")
            time.sleep(BUCKET_CHECK_DELAY_SECONDS)

        raise ObjectStorageError("Object storage did not become ready") from last_error

    def create_upload_form(self, key: str, size: int) -> tuple[str, dict[str, str]]:
        with _storage_errors():
            form: dict[str, Any] = self._client.generate_presigned_post(
                Bucket=self._bucket,
                Key=key,
                Fields={"Content-Type": UPLOAD_CONTENT_TYPE},
                Conditions=[
                    {"Content-Type": UPLOAD_CONTENT_TYPE},
                    ["content-length-range", size, size],
                ],
                ExpiresIn=UPLOAD_FORM_EXPIRES_SECONDS,
            )
        return self._public_url, form["fields"]

    def get_object_size(self, key: str) -> int | None:
        with _storage_errors():
            try:
                response: HeadObjectOutputTypeDef = self._client.head_object(
                    Bucket=self._bucket, Key=key
                )
            except ClientError as error:
                if _http_status(error) == 404:
                    return None
                raise
        return response["ContentLength"]

    def read_object(self, key: str, chunk_size: int) -> Generator[bytes] | None:
        with _storage_errors():
            try:
                response: GetObjectOutputTypeDef = self._client.get_object(
                    Bucket=self._bucket, Key=key
                )
            except ClientError as error:
                if _http_status(error) == 404:
                    return None
                raise
        chunks: Generator[bytes] = self._read_chunks(response["Body"], chunk_size)
        # started up to its try, so closing it before the first read still closes the body
        next(chunks)
        return chunks

    def _read_chunks(self, body: StreamingBody, chunk_size: int) -> Generator[bytes]:
        try:
            yield b""
            with _storage_errors():
                yield from body.iter_chunks(chunk_size)
        finally:
            body.close()

    def list_objects(self, prefix: str) -> Iterator[list[StoredObject]]:
        paginator: ListObjectsV2Paginator = self._client.get_paginator(
            "list_objects_v2"
        )
        with _storage_errors():
            for page in paginator.paginate(
                Bucket=self._bucket,
                Prefix=prefix,
                PaginationConfig={"PageSize": DELETE_BATCH_SIZE},
            ):
                yield [
                    StoredObject(key=obj["Key"], last_modified=obj["LastModified"])
                    for obj in page.get("Contents", [])
                    if "Key" in obj and "LastModified" in obj
                ]

    def delete_objects(self, keys: list[str]) -> None:
        for start in range(0, len(keys), DELETE_BATCH_SIZE):
            batch: list[str] = keys[start : start + DELETE_BATCH_SIZE]
            with _storage_errors():
                response: DeleteObjectsOutputTypeDef = self._client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
                )
            for error in response.get("Errors", []):
                logger.error(
                    f"Could not delete object {error.get('Key')}: {error.get('Code')}"
                )

    def delete_folders_quietly(self, prefixes: list[str]) -> None:
        for prefix in prefixes:
            try:
                for page in self.list_objects(prefix):
                    self.delete_objects([obj.key for obj in page])
            except ObjectStorageError:
                # objects left without a file are deleted later as orphans
                logger.exception(f"Could not delete the folder {prefix}")

    def _bucket_exists(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self._bucket)
            return True
        except ClientError as error:
            if _http_status(error) == 404:
                return False
            raise
