from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from services import (
    ConflictError,
    Json,
    JsonObject,
    Link,
    Record,
    RecordStore,
    Tx,
)
from services.ograg.ontology import (
    JSONLD_ID,
    JSONLD_TYPE,
    Ontology,
    Property,
    get_link_target_id,
    get_local_name,
    get_type,
    to_list,
)

log = logging.getLogger(__name__)
# write in service's transaction is retried after a ConflictError
WRITE_ATTEMPTS: int = 3
LINK_NOT_FOUND: str = "does not exist"
LINK_WRONG_CLASS: str = "is a {cls}"
ERROR_UNREACHABLE: str = "unreachable"
ERROR_NOT_RECORD_CLASS: str = "a record must be one of {classes}, not {cls!r}"
ERROR_NO_PROPERTIES: str = "record has no {cls} properties"
ERROR_CLASS_CHANGED: str = (
    "{record_id!r} is a {old_cls}, delete it before storing a {new_cls}"
)
ERROR_BAD_LINK: str = (
    "property {prop_name} links to {target_id!r}, which {problem}, not a {expected_cls}"
)
REVIEW_LOST_LAST_LINK: str = "Lost its last link: {cls} {deleted_id} was deleted."
# class in ``REVIEW_LOST_LAST_LINK`` when deleted record could not be read
REVIEW_UNKNOWN_CLASS: str = "record"


@dataclass(frozen=True)
class DeleteResult:
    """Result of ``OgRagService.delete_record``.

    Attributes:
        deleted_ids: deleted record ids: record, then orphans (if ``delete_orphans`` was ``True``). Empty: no such record.
        marked_ids: ids of records that lost their last parent link and were marked for review.
    """

    deleted_ids: list[str] = field(default_factory=list)
    marked_ids: list[str] = field(default_factory=list)


@dataclass
class _Deletion:
    """Progress of a ``OgRagService.delete_record`` call. What's still to delete, and records changed on the way."""

    ids_to_delete: list[str]
    delete_orphans: bool
    result: DeleteResult = field(default_factory=DeleteResult)
    unlinked: dict[str, Record] = field(
        default_factory=dict
    )  # id -> record without its links to deleted ones


class RecordError(ValueError):
    """Record cannot be stored and does not fit the ontology:
    - id belongs to a record of another class
    - or a link points to a missing record or one of the wrong class.
    """


class OgRagService:
    """Service to store and read records and their index. Holds no state between requests. Holds no data on its own."""

    def __init__(
        self,
        ontology: Ontology,
        store: RecordStore,
    ):
        """
        Args:
            ontology: ontology to validate records with. Record classes may be stored.
            store: where records are stored.
        """
        self.ontology, self.store = ontology, store

    async def upsert_record(
        self,
        record_id: str,
        node: Mapping[str, Json],
        tx: Tx | None = None,
        author: str | None = None,
    ) -> list[str]:
        """Validates ``node`` and update-or-inserts it as a record. Saving a record clears its ``review``.

        Args:
            record_id: becomes the ``node``'s ``@id``.
            node: JSON-LD node of a record class (``@type``, defaults to anchor class). Undefined properties are dropped. Links hold the target's id (or ``{"@id": ...}``).
            tx: transaction, or ``None``.
            author: ``og:author``, replaces ``node``'s value.

        Returns:
            Warnings: validation drops.

        Raises:
            RecordError:
                - class is not a record class
                - id belongs to a record of another class
                - no valid property is left
                - or a link points to a missing record or one of the wrong class.
            UnstorableValueError: store cannot store given value.
            ConflictError: detected concurrent write. If ``tx`` wasn't ``None``, raises immediately without retry.
        """
        cls: str = self._get_record_class(node)
        submitted: JsonObject = self._get_submitted(record_id, cls, node, author)
        record, warnings = self._validate_record(record_id, cls, submitted)
        await self._run_with_retries(lambda own: self._write_record(record, own), tx)
        return warnings

    async def delete_record(
        self, record_id: str, tx: Tx | None = None, delete_orphans: bool = False
    ) -> DeleteResult:
        """Deletes a record and removes it from records that link to it.

        If ``delete_orphans`` is ``True``, deletes records that lost their last parent link. Otherwise marked for manual review.

        Args:
            record_id: record id.
            tx: transaction, or ``None``.
            delete_orphans: whether to delete records left without a parent link.

        Returns:
            Deleted ids (or empty) and ids marked for review.

        Raises:
            ConflictError: detected concurrent write. If ``tx`` wasn't ``None``, raises immediately without retry.
        """
        return await self._run_with_retries(
            lambda own: self._delete_with_links(record_id, delete_orphans, own), tx
        )

    async def get_record(self, record_id: str, tx: Tx | None = None) -> Record | None:
        """Returns record of ``record_id``, or ``None``."""
        return await self.store.get_record(record_id, tx)

    async def get_records_to_review(self, tx: Tx | None = None) -> list[Record]:
        """Returns records marked for review."""
        return await self.store.get_records_to_review(tx)

    async def get_records(self, tx: Tx | None = None) -> dict[str, JsonObject]:
        """Returns all stored (validated) records."""
        return {rec.id: rec.graph for rec in await self.store.get_all_records(tx)}

    async def _run_with_retries[T](
        self, write: Callable[[Tx], Awaitable[T]], tx: Tx | None
    ) -> T:
        """Runs a ``write`` in ``tx``. Or in store's transaction, retried after a ``ConflictError``."""
        for attempt in range(WRITE_ATTEMPTS):
            try:
                async with self.store.open_transaction(tx) as own:
                    return await write(own)
            except ConflictError:
                if tx is not None or attempt == WRITE_ATTEMPTS - 1:
                    raise
        raise AssertionError(ERROR_UNREACHABLE)

    def _get_record_class(self, node: Mapping[str, Json]) -> str:
        """Returns ``node``'s record class (defaults to anchor class).

        Raises:
            RecordError: class is not a record class.
        """
        cls: str = get_type(node, self.ontology.anchor_class)
        if cls not in self.ontology.record_classes:
            raise RecordError(
                ERROR_NOT_RECORD_CLASS.format(
                    classes=self.ontology.record_classes, cls=cls
                )
            )
        return cls

    def _get_submitted(
        self, record_id: str, cls: str, node: Mapping[str, Json], author: str | None
    ) -> JsonObject:
        """Returns unvalidated ``node``, with ``cls``, ``record_id`` and, if given, ``author``, to be kept as stored input."""
        submitted: JsonObject = {**node, JSONLD_TYPE: cls, JSONLD_ID: record_id}
        if author is not None:
            submitted.update(
                {name: author for name in self._get_author_property_names(cls)}
            )
        return submitted

    def _get_author_property_names(self, cls: str) -> list[str]:
        """Returns property names of ``cls`` that hold the author."""
        return [
            prop.name
            for (domain, _), prop in self.ontology.properties.items()
            if domain == cls and prop.author
        ]

    def _validate_record(
        self, record_id: str, cls: str, submitted: JsonObject
    ) -> tuple[Record, list[str]]:
        """Returns validated record from ``submitted``, and the validation drop warnings.

        Raises:
            RecordError: node properties don't fit the ontology.
        """
        graph, warnings = self.ontology.validate_node(submitted, cls)
        if not set(graph) - {JSONLD_TYPE, JSONLD_ID}:
            raise RecordError(
                "; ".join(warnings) or ERROR_NO_PROPERTIES.format(cls=cls)
            )
        links: tuple[Link, ...] = tuple(self.ontology.get_links(graph))
        return Record(
            record_id, cls, graph, submitted, self.ontology.version, links
        ), warnings

    async def _write_record(self, record: Record, tx: Tx) -> None:
        """Locks, checks, saves and indexes the ``record``. All in ``tx``.

        Shared locks on parents. Do **NOT** lock link targets, otherwise two items that link each other can deadlock.
        """
        await self._check_class_is_kept(record, tx)
        for link in record.links:
            await self._check_link_target(record, link, tx)
        await self.store.save_records([record], tx)

    async def _check_class_is_kept(self, record: Record, tx: Tx) -> None:
        """
        Raises:
            RecordError: id of ``record`` already belongs to a record of another class.
        """
        existing: Record | None = await self.store.get_record(record.id, tx)
        if existing is not None and existing.cls != record.cls:
            raise RecordError(
                ERROR_CLASS_CHANGED.format(
                    record_id=record.id, old_cls=existing.cls, new_cls=record.cls
                )
            )

    async def _check_link_target(self, record: Record, link: Link, tx: Tx) -> None:
        """
        Raises:
            RecordError:
                - target of ``link`` doesn't exist
                - or target of ``link`` doesn't have the class its property expects.
        """
        expected_cls: str = self.ontology.properties[
            record.cls, link.property_name
        ].range
        actual_cls: str | None = await self._get_class_of(link.target_id, record, tx)
        if actual_cls != expected_cls:
            problem = (
                LINK_NOT_FOUND
                if actual_cls is None
                else LINK_WRONG_CLASS.format(cls=actual_cls)
            )
            raise RecordError(
                ERROR_BAD_LINK.format(
                    prop_name=link.property_name,
                    target_id=link.target_id,
                    problem=problem,
                    expected_cls=expected_cls,
                )
            )

    async def _get_class_of(
        self, record_id: str, writing: Record, tx: Tx
    ) -> str | None:
        if record_id == writing.id:
            return writing.cls
        found: Record | None = await self.store.get_record(record_id, tx)
        return None if found is None else found.cls

    async def _delete_with_links(
        self, record_id: str, delete_orphans: bool, tx: Tx
    ) -> DeleteResult:
        """Deletes the record, first unlinking it from everywhere. Deletes orphans if asked to."""
        if await self.store.get_record(record_id, tx) is None:
            return DeleteResult()

        run = _Deletion(ids_to_delete=[record_id], delete_orphans=delete_orphans)
        while run.ids_to_delete:
            id_to_delete: str = run.ids_to_delete.pop(0)
            await self._unlink_from_linking_records(id_to_delete, run, tx)
            await self.store.delete_record(id_to_delete, tx)
            run.result.deleted_ids.append(id_to_delete)
            run.unlinked.pop(id_to_delete, None)
        return run.result

    async def _unlink_from_linking_records(
        self, id_to_delete: str, run: _Deletion, tx: Tx
    ) -> None:
        """Removes the links to ``id_to_delete`` from every record. Orphans are marked or queued for deletion."""
        record_to_delete: Record | None = await self.store.get_record(id_to_delete, tx)
        for linking in await self._get_linking_records(
            id_to_delete, run.result.deleted_ids, tx
        ):
            unlinked: Record = self._unlink(linking, id_to_delete)
            if linking.id not in run.ids_to_delete and self._has_lost_last_parent(
                linking, unlinked
            ):
                if run.delete_orphans:
                    run.ids_to_delete.append(linking.id)
                else:
                    unlinked = replace(
                        unlinked,
                        review=self._get_review_note(id_to_delete, record_to_delete),
                    )
                    run.result.marked_ids.append(linking.id)
            await self.store.save_records([unlinked], tx)
            run.unlinked[linking.id] = unlinked

    async def _get_linking_records(
        self, target_id: str, deleted_ids: Sequence[str], tx: Tx
    ) -> list[Record]:
        """Returns records still linking to ``target_id``, excluding itself and ``deleted_ids``."""
        linking: list[Record] = await self.store.get_linking_records([target_id], tx)
        linking_ids: list[str] = [
            rec.id
            for rec in linking
            if rec.id != target_id and rec.id not in deleted_ids
        ]
        return await self.store.get_records(linking_ids, tx)

    def _has_lost_last_parent(self, before: Record, after: Record) -> bool:
        """Returns whether unlinking deleted the record's last parent link."""
        return bool(self._get_parent_ids(before)) and not self._get_parent_ids(after)

    @staticmethod
    def _get_review_note(deleted_id: str, deleted_record: Record | None) -> str:
        cls: str = deleted_record.cls if deleted_record else REVIEW_UNKNOWN_CLASS
        return REVIEW_LOST_LAST_LINK.format(cls=cls, deleted_id=deleted_id)

    def _unlink(self, record: Record, target_id: str) -> Record:
        """Returns ``record`` without its links to ``target_id`` (in graph and input), validated again."""
        link_names: set[str] = self.ontology.get_link_names(record.cls)
        submitted: JsonObject = self._drop_links_to(record.input, link_names, target_id)
        graph, _ = self.ontology.validate_node(submitted, record.cls)
        return replace(
            record,
            graph=graph,
            input=submitted,
            links=tuple(self.ontology.get_links(graph)),
        )

    @staticmethod
    def _drop_links_to(
        node: Mapping[str, Json], link_names: set[str], target_id: str
    ) -> JsonObject:
        """Returns ``node`` with ``target_id`` removed from its links. An empty link is deleted."""
        kept_node: JsonObject = {}
        for key, value in node.items():
            if get_local_name(key) in link_names:
                kept: list[Json] = [
                    val
                    for val in to_list(value)
                    if str(get_link_target_id(val)) != target_id
                ]
                if not kept:
                    continue
                value: Json | list[Json] = kept if isinstance(value, list) else kept[0]
            kept_node[key] = value
        return kept_node

    def _get_parent_ids(self, record: Record) -> list[str]:
        """Returns parent ids of ``record``, each once."""
        parent_ids: dict[str, None] = {}
        for link in record.links:
            prop: Property | None = self.ontology.properties.get(
                (record.cls, link.property_name)
            )
            if prop is not None and prop.is_parent_link:
                parent_ids.setdefault(link.target_id)
        return list(parent_ids)
