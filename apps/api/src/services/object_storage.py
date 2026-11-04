from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from datetime import datetime


class ObjectStorageError(Exception):
    """The object storage failed or could not be reached."""


@dataclass(frozen=True)
class StoredObject:
    key: str
    last_modified: datetime


class ObjectStorage(ABC):
    """Files stored by key in one bucket. Blocking: call it with ``asyncio.to_thread`` from async code.

    Every method raises ``ObjectStorageError`` when the storage fails, ``delete_folders_quietly`` excepted.
    """

    @abstractmethod
    def ensure_bucket(self) -> None:
        """Creates the bucket if it does not exist, waiting for the storage to start."""
        ...

    @abstractmethod
    def create_upload_form(self, key: str, size: int) -> tuple[str, dict[str, str]]:
        """Returns the URL and the fields of a form the browser posts the file of exactly ``size`` bytes with."""
        ...

    @abstractmethod
    def get_object_size(self, key: str) -> int | None:
        """Returns the size of the object, ``None`` if it does not exist."""
        ...

    @abstractmethod
    def read_object(self, key: str, chunk_size: int) -> Generator[bytes] | None:
        """Returns the object's content in chunks, ``None`` if it does not exist.

        Close the generator when done, also when stopping early: it holds the connection.
        """
        ...

    @abstractmethod
    def list_objects(self, prefix: str) -> Iterator[list[StoredObject]]:
        """Yields the objects under ``prefix``, one page at a time."""
        ...

    @abstractmethod
    def delete_objects(self, keys: list[str]) -> None:
        """Deletes the objects. Logs the ones that could not be deleted."""
        ...

    @abstractmethod
    def delete_folders_quietly(self, prefixes: list[str]) -> None:
        """Deletes every object under each prefix, logs a failure instead of raising."""
        ...
