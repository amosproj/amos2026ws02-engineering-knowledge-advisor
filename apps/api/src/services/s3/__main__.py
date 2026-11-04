"""Creates the bucket if it does not exist yet. Run with `python -m services.s3`."""

import logging

from config.settings import get_settings
from services.s3.storage import S3ObjectStorage

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    S3ObjectStorage(get_settings()).ensure_bucket()
