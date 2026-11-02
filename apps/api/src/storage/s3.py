import logging
import time
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectionError,
    HTTPClientError,
)

from config.settings import get_settings
from logger import logger

BUCKET_CHECK_ATTEMPTS = 30
BUCKET_CHECK_DELAY_SECONDS = 2
UPLOAD_FORM_EXPIRES_SECONDS = 3600
UPLOAD_CONTENT_TYPE = "application/octet-stream"
DELETE_BATCH_SIZE = 1000


@lru_cache
def get_s3_client() -> Any:
    settings = get_settings()
    return boto3.client(
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


def _http_status(error: ClientError) -> int:
    return error.response["ResponseMetadata"]["HTTPStatusCode"]


def _bucket_exists(client: Any, bucket: str) -> bool:
    try:
        client.head_bucket(Bucket=bucket)
        return True
    except ClientError as error:
        if _http_status(error) == 404:
            return False
        raise


def ensure_bucket() -> None:
    client = get_s3_client()
    bucket = get_settings().s3_bucket
    last_error: Exception | None = None

    for _ in range(BUCKET_CHECK_ATTEMPTS):
        try:
            if _bucket_exists(client, bucket):
                logger.info(f"Bucket {bucket} already exists")
            else:
                client.create_bucket(Bucket=bucket)
                logger.info(f"Created bucket {bucket}")
            return
        except ClientError as error:
            if _http_status(error) < 500:
                raise
            last_error = error
        except (ConnectionError, HTTPClientError) as error:
            last_error = error

        logger.info("Object storage is not ready yet, retrying")
        time.sleep(BUCKET_CHECK_DELAY_SECONDS)

    raise RuntimeError("Object storage did not become ready") from last_error


def create_upload_form(key: str, size: int) -> tuple[str, dict[str, str]]:
    settings = get_settings()
    form = get_s3_client().generate_presigned_post(
        Bucket=settings.s3_bucket,
        Key=key,
        Fields={"Content-Type": UPLOAD_CONTENT_TYPE},
        Conditions=[
            {"Content-Type": UPLOAD_CONTENT_TYPE},
            ["content-length-range", size, size],
        ],
        ExpiresIn=UPLOAD_FORM_EXPIRES_SECONDS,
    )
    # The browser reaches MinIO through a same-origin proxy, not the internal endpoint
    url = f"{settings.s3_public_url.rstrip('/')}/{settings.s3_bucket}"
    return url, form["fields"]


def get_object_size(key: str) -> int | None:
    try:
        response = get_s3_client().head_object(Bucket=get_settings().s3_bucket, Key=key)
    except ClientError as error:
        if _http_status(error) == 404:
            return None
        raise
    return response["ContentLength"]


def open_object(key: str) -> Any | None:
    """Return the object body as a stream, None if the object does not exist."""
    try:
        response = get_s3_client().get_object(Bucket=get_settings().s3_bucket, Key=key)
    except ClientError as error:
        if _http_status(error) == 404:
            return None
        raise
    return response["Body"]


def list_objects(prefix: str) -> Iterator[list[dict[str, Any]]]:
    """Yield the objects under the prefix, one page of up to DELETE_BATCH_SIZE at a time."""
    paginator = get_s3_client().get_paginator("list_objects_v2")
    for page in paginator.paginate(
        Bucket=get_settings().s3_bucket,
        Prefix=prefix,
        PaginationConfig={"PageSize": DELETE_BATCH_SIZE},
    ):
        yield page.get("Contents", [])


def delete_object(key: str) -> None:
    get_s3_client().delete_object(Bucket=get_settings().s3_bucket, Key=key)


def delete_object_quietly(key: str) -> None:
    try:
        delete_object(key)
    except (BotoCoreError, ClientError):
        logger.exception(f"Could not delete object {key}")


def delete_objects(keys: list[str]) -> None:
    """Delete up to DELETE_BATCH_SIZE objects in one request."""
    if not keys:
        return
    response = get_s3_client().delete_objects(
        Bucket=get_settings().s3_bucket,
        Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
    )
    for error in response.get("Errors", []):
        logger.error(f"Could not delete object {error['Key']}: {error['Code']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ensure_bucket()
