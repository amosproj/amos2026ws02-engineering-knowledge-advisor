S3_ENV: dict[str, str] = {
    "API_S3_ENDPOINT_URL": "http://localhost:9000",
    "API_S3_BUCKET": "test",
    "API_S3_ACCESS_KEY": "test",
    "API_S3_SECRET_KEY": "test",
    "API_S3_REGION": "us-east-1",
    "API_S3_PUBLIC_URL": "/storage",
}


def assert_mentions(text: str, *words: str) -> None:
    """Asserts that ``text`` contains each of ``words`` (case ignore)."""
    missing: list[str] = [
        word for word in words if word.casefold() not in text.casefold()
    ]
    assert not missing, f"{missing} not in {text!r}"
