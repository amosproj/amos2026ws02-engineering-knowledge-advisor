from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from services.database import ConflictError, Tx
from services.json_types import JsonObject

ERROR_STILL_LINKED: str = "{record_id!r} is still linked from {linking_ids}"


class RecordLinkedError(ConflictError):
    """Tried to delete record that is linked to by others. This may be a reason for a transaction rollback.

    e.g. concurrent record link write
    """


@dataclass(frozen=True)
class Link:
    """Record link.

    Attributes:
        property_name: name of property that holds the link.
        target_id: id of the linked record.
    """

    property_name: str
    target_id: str


@dataclass(frozen=True)
class Record:
    """Ontology-validated node. Includes input it was parsed from and links.

    Attributes:
        id: unique id (node's ``@id``).
        cls: record class.
        graph: validated JSON-LD node with nested nodes, record's part of the knowledge graph. This is what's indexed and searched.
        input: node as submitted (or extracted from a document). Requires re-validation on ontology change.
        ontology_version: the ``Ontology.version`` the graph was validated with.
        links: graph's links (``Ontology.get_links``).
        review: empty, or why the record needs a review (e.g. last parent link was deleted).
    """

    id: str
    cls: str
    graph: JsonObject
    input: JsonObject
    ontology_version: str
    links: tuple[Link, ...] = ()
    review: str = ""


class RecordStore(Protocol):
    """Stores records. Stored records are source of truth.

    Contract:
        - all methods with ``tx``: execute in ``tx`` when provided, but don't commit. If `None`, methods commit on their own.
        - ``save_records`` stores each record's ``links`` and replaces its earlier ones.
        - ``delete_record`` removes the record's own links and refuses (``RecordLinkedError``) if other records link to it.
        - Methods raise ``UnstorableValueError`` for values that cannot be stored or compared, and ``ConflictError`` for a collision to be resolved by retry.
    """

    @abstractmethod
    async def save_records(
        self, records: Sequence[Record], tx: Tx | None = None
    ) -> None:
        """Creates ``records``, or replaces them in entirety without merge. All-or-nothing: either all are written, or none.

        Args:
            records: records to write, if id already exists the record is replaced.
            tx: transaction, or ``None``.
        """
        ...

    @abstractmethod
    async def get_record(self, record_id: str, tx: Tx | None = None) -> Record | None:
        """Returns a record.

        Args:
            record_id: record id.
            tx: transaction, or ``None``.

        Returns:
            Requested record, or ``None``.
        """
        ...

    @abstractmethod
    async def delete_record(self, record_id: str, tx: Tx | None = None) -> bool:
        """Deletes one record.

        Args:
            record_id: record id.
            tx: transaction, or ``None``.

        Returns:
            ``True`` if deleted, ``False`` if record wasn't found.

        Raises:
            RecordLinkedError: other records link to it, cannot delete.
        """
        ...

    @abstractmethod
    async def get_all_records(self, tx: Tx | None = None) -> list[Record]:
        """Returns every record, sorted by id.

        Args:
            tx: transaction, or ``None``.
        """
        ...

    @abstractmethod
    async def get_records(
        self, record_ids: Sequence[str], tx: Tx | None = None
    ) -> list[Record]:
        """Returns records by ``record_ids`` in one batch.

        Args:
            record_ids: ids to read, may be thousands. Ids without a record are ignored.
            tx: transaction, or ``None``.

        Returns:
            Found records, in any order.
        """
        ...

    @abstractmethod
    def open_transaction(self, tx: Tx | None = None) -> AbstractAsyncContextManager[Tx]:
        """Returns ``tx``, or transaction belonging to store that commits on exit and rolls back on error."""
        ...

    @abstractmethod
    async def get_ontology_versions(self, tx: Tx | None = None) -> dict[str, int]:
        """Returns the aggregate record count per ``ontology_version``."""
        ...

    @abstractmethod
    async def get_linking_records(
        self, target_ids: Sequence[str], tx: Tx | None = None
    ) -> list[Record]:
        """Returns records with a link to any of ``target_ids``.

        Args:
            target_ids: ids of link targets.
            tx: transaction, or ``None``.

        Returns:
            Linking records sorted by id, each once.
        """
        ...

    @abstractmethod
    async def get_records_to_review(self, tx: Tx | None = None) -> list[Record]:
        """Returns the records whose ``review`` is not empty.

        Args:
            tx: transaction, or ``None``.

        Returns:
            Records sorted by id.
        """
        ...

    @abstractmethod
    async def find_record_ids(
        self, cls: str, text: str, tx: Tx | None = None
    ) -> list[str]:
        """Returns record ids of class ``cls`` whose id or an identity value equals ``text``, ignoring case.

        Which properties are identity properties is defined in ontology.

        Args:
            cls: record class.
            text: name or identifier as written.
            tx: transaction, or ``None``.

        Returns:
            Sorted, matching record ids. More than one means the reference is ambiguous.
        """
        ...
