from __future__ import annotations

from enum import StrEnum


class SearchMode(StrEnum):
    """How a property's values are searched (``og:search``). Members are plain strings."""

    SEMANTIC = "semantic"
    """By meaning (embeddings). Default for text."""
    LEXICAL = "lexical"
    """By spelling (``pg_trgm``). For identifiers and names."""
    FILTER = "filter"
    """As a number for filters. Default for numbers."""
