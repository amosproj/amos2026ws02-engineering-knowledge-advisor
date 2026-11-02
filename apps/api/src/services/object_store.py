from __future__ import annotations

from abc import abstractmethod
from typing import Protocol


class ObjectStore(Protocol):
    """Store for document originals.

    Writes on upload, reads for (re-)extraction, deletes with the document.
    Not transactional: file whose upload was rolled back may be left behind.
    PUT with existing key must succeed (same key = same content).
    """

    @abstractmethod
    async def put_object(self, key: str, data: bytes, media_type: str) -> str:
        """Stores a file.

        Args:
            key: unique name, ``"<document id><suffix>"`` (e.g. ``"doc-123.md"``). Key equality implies content equality.
            data: file bytes.
            media_type: e.g. ``"text/markdown"``

        Returns:
            Stored object URI
        """
        ...

    @abstractmethod
    async def get_object(self, uri: str) -> bytes:
        """Reads a file.

        Raises:
            OSError: if missing, or cannot be read
        """
        ...

    @abstractmethod
    async def delete_object(self, uri: str) -> None:
        """Deletes a file. No error throw if already deleted."""
        ...
