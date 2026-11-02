from __future__ import annotations

from abc import abstractmethod
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from services.database import Tx
from services.json_types import JsonObject

if TYPE_CHECKING:  # at runtime it would be circular as ontology imports from services
    from services.ograg.ontology import Ontology


class DocumentStatus(StrEnum):
    """Extraction state of a document (``Document.status``). Members are plain strings."""

    PENDING = "pending"
    """Added, not extracted yet."""
    EXTRACTED = "extracted"
    """Records extracted."""
    FAILED = "failed"
    """Last extraction failed (``Document.error`` says why)."""


@dataclass(frozen=True)
class Document:
    """An uploaded document. The file lives in the ``ObjectStore``.

    Attributes:
        id: ``"doc-"`` + the start of the content's SHA-256.
        uri: where the ``ObjectStore`` keeps the file (returned by ``ObjectStore.put_object``).
        media_type: e.g. ``"text/markdown"``, ``"text/plain"``.
        sha256: SHA-256 of the file bytes.
        file_name: name of uploaded file.
        status: see ``DocumentStatus``.
        error: empty, or why last extraction failed.
        notes: what last extraction skipped.
        extractor_name: ``KnowledgeExtractor.name`` of last extraction (provenance).
        property_paths: ``"Class.property"`` paths extracted so far. Used by migration to find docs that were extracted before a property existed.
        meta: any additional data.
        author: uploader of the document.
    """

    id: str
    uri: str
    media_type: str
    sha256: str
    file_name: str = ""
    status: DocumentStatus = DocumentStatus.PENDING
    error: str = ""
    notes: list[str] = field(default_factory=list)
    extractor_name: str = ""
    property_paths: list[str] = field(default_factory=list)
    meta: JsonObject = field(default_factory=dict)
    author: str = ""


@dataclass(frozen=True)
class Passage:
    """Passage from a text document. Produced by a ``TextExtractor``. Should be at most a few thousand characters.

    Attributes:
        text: freeform text.
        location: where in the document, e.g. ``"paragraph 3"``, ``"Laser cell, paragraph 2, part 1"``, ``"page 4"``.
    """

    text: str
    location: str = ""


@dataclass(frozen=True)
class Extracted:
    """Candidate record found in a document. Produced by a ``KnowledgeExtractor``. Not yet validated.

    Attributes:
        node: JSON-LD node of a record class (``@type``). ``@id`` is a key for the entity, the same in every extraction of the same document.
        passage_indexes: indexes into the passages the candidate rests on (evidence).
    """

    node: JsonObject
    passage_indexes: list[int] = field(default_factory=list)


class DocumentStore(Protocol):
    """Stores documents (``Document``) and which records were extracted from which document.

    A link must be deleted when its record is deleted (Postgres: a foreign key with ``ON DELETE CASCADE``).
    ``get_records_of`` and ``get_documents_of`` never return deleted records.
    """

    @abstractmethod
    async def save_document(self, document: Document, tx: Tx | None = None) -> None:
        """Creates, replaces or updates ``document``."""
        ...

    @abstractmethod
    async def get_document(
        self, document_id: str, tx: Tx | None = None
    ) -> Document | None:
        """Returns a document. ``None`` if there is none."""
        ...

    @abstractmethod
    async def get_all_documents(self, tx: Tx | None = None) -> list[Document]:
        """Returns every document sorted by id."""
        ...

    @abstractmethod
    async def delete_document(self, document_id: str, tx: Tx | None = None) -> bool:
        """Deletes a document and its links (not its records, that's done by ``DocumentService.delete``).

        Returns:
            ``True`` if document was successfully deleted.
        """
        ...

    @abstractmethod
    async def set_document_records(
        self, document_id: str, record_ids: Sequence[str], tx: Tx | None = None
    ) -> None:
        """Replaces the document's links to records with ``record_ids`` (records themselves remain untouched)."""
        ...

    @abstractmethod
    async def get_records_of(self, document_id: str, tx: Tx | None = None) -> list[str]:
        """Returns the sorted ids of the records extracted from a document."""
        ...

    @abstractmethod
    async def get_documents_of(self, record_id: str, tx: Tx | None = None) -> list[str]:
        """Returns the sorted ids of the documents a record was extracted from."""
        ...


class TextExtractor(Protocol):
    """Extracts text passages from a document."""

    @abstractmethod
    def supports_media_type(self, media_type: str) -> bool:
        """Returns whether ``extract_passages`` can read a media type."""
        ...

    @abstractmethod
    async def extract_passages(self, data: bytes, media_type: str) -> list[Passage]:
        """Splits a document into passages in reading order.

        Args:
            data: file content.
            media_type: file media type (``supports`` should return ``True``).

        Returns:
            Text passages with locations. Their size only sets how precisely evidence points into the text.
            ``KnowledgeExtractor`` groups them into larger chunks per LLM call, so small passages cost no extra calls.

        Raises:
            ValueError: ``data`` cannot be read.
        """
        ...


class KnowledgeExtractor(Protocol):
    """Turns passages into candidate records.

    Attributes:
        name: method, model and prompt version, e.g. ``"claude:claude-opus-5-5+extraction-v1"``. Kept on ``Document`` as provenance.
    """

    name: str

    @abstractmethod
    async def extract_records(
        self,
        passages: Sequence[Passage],
        ontology: Ontology,
        only: Collection[tuple[str, str]] | None = None,
    ) -> list[Extracted]:
        """Extracts records from ``passages`` based on ``ontology``.

        Args:
            passages: document's passages in order.
            ontology: record class and property definitions.
            only: extract only these (class, property) pairs plus the classes nesting them. ``None`` means everything.

        Returns:
            One candidate per entity. Entity that was found twice should be merged.

        Raises:
            LLMError: provider failure.
        """
        ...
