def assert_mentions(text: str, *words: str) -> None:
    """Asserts that ``text`` contains each of ``words`` (case ignore)."""
    missing: list[str] = [
        word for word in words if word.casefold() not in text.casefold()
    ]
    assert not missing, f"{missing} not in {text!r}"
