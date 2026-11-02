import logging
import time
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ConnectionError, HTTPClientError

from config.settings import get_settings
from logger import logger

BUCKET_CHECK_ATTEMPTS = 30
BUCKET_CHECK_DELAY_SECONDS = 2
UPLOAD_FORM_EXPIRES_SECONDS = 3600
UPLOAD_CONTENT_TYPE = "application/octet-stream"


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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ensure_bucket()
