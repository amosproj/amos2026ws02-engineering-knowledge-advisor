from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace

from services import (
    ConflictError,
    Json,
    JsonObject,
    Link,
    Record,
    RecordStore,
    StaleVersionError,
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
from services.records import ANY_VERSION, ERROR_STALE_VERSION

log = logging.getLogger(__name__)
# write in service's transaction is retried after a ConflictError
WRITE_ATTEMPTS: int = 3
LINK_NOT_FOUND: str = "does not exist"
LINK_WRONG_CLASS: str = "is a {cls}"
ERROR_UNREACHABLE: str = "unreachable"
ERROR_NOT_RECORD_CLASS: str = "a record must be one of {classes}, not {cls!r}"
ERROR_NO_PROPERTIES: str = "record has no {cls} properties"
ERROR_IDENTITY_REQUIRED: str = "a {cls} needs a non-blank value in one of {prop_names}"
ERROR_PARENT_LOOP: str = (
    "{cls} {record_id!r} would become its own ancestor through {prop_names}"
)
ERROR_CLASS_CHANGED: str = (
    "{record_id!r} is a {old_cls}, delete it before storing a {new_cls}"
)
ERROR_MAX_PER_PARENT: str = (
    "{target_id!r} already has {limit} {cls} through {prop_name}, the most it may have"
)
MAX_PER_PARENT: str = "max_per_parent"
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


class ParentLimitError(Exception):
    """A parent already has as many records of the class through the link as ``og:maxPerParent`` allows."""

    error_code: str = MAX_PER_PARENT


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
        expected_versions: Collection[str] | None = None,
    ) -> list[str]:
        """Validates ``node`` and update-or-inserts it as a record. Saving a record clears its ``review``.

        Args:
            record_id: becomes the ``node``'s ``@id``.
            node: JSON-LD node of a record class (``@type``, defaults to anchor class). Undefined properties are dropped. Links hold the target's id (or ``{"@id": ...}``).
            tx: transaction, or ``None``.
            expected_versions: versions to match (``check_version``).

        Returns:
            Warnings: validation drops.

        Raises:
            RecordError:
                - class is not a record class
                - id belongs to a record of another class
                - no valid property is left
                - class has identity properties, but none holds a non-blank value
                - or a link points to a missing record or one of the wrong class.
            ParentLimitError: a parent the record newly links to is full (``og:maxPerParent``).
            UnstorableValueError: store cannot store given value.
            ConflictError: detected concurrent write. If ``tx`` wasn't ``None``, raises immediately without retry.
            StaleVersionError: record has none of ``expected_versions``.
        """
        cls: str = self._get_record_class(node)
        submitted: JsonObject = self._get_submitted(record_id, cls, node)
        record, warnings = self._validate_record(record_id, cls, submitted)
        await self._run_with_retries(
            lambda own: self._write_record(record, own, expected_versions), tx
        )
        return warnings

    async def check_version(
        self, record_id: str, expected_versions: Collection[str] | None, tx: Tx
    ) -> None:
        """Locks the record and checks its version (``If-Match``).

        Args:
            record_id: record id.
            expected_versions: versions to match, ``ANY_VERSION`` matches any. ``None`` skips the check.
            tx: transaction, holds the lock.

        Raises:
            StaleVersionError: other version, or no such record.
        """
        if expected_versions is None:
            return
        current: str | None = await self.store.lock_record(record_id, tx)
        if current is None or not (
            ANY_VERSION in expected_versions or current in expected_versions
        ):
            raise StaleVersionError(
                ERROR_STALE_VERSION.format(
                    record_id=record_id, expected_versions=sorted(expected_versions)
                )
            )

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

    async def get_records(self, tx: Tx | None = None) -> list[JsonObject]:
        """Returns all stored (validated) records."""
        return [
            {**rec.graph, JSONLD_ID: rec.id}
            for rec in await self.store.get_all_records(tx)
        ]

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
        self, record_id: str, cls: str, node: Mapping[str, Json]
    ) -> JsonObject:
        """Returns unvalidated ``node``, with ``cls`` and ``record_id``, to be kept as stored input."""
        return {**node, JSONLD_TYPE: cls, JSONLD_ID: record_id}

    def _validate_record(
        self, record_id: str, cls: str, submitted: JsonObject
    ) -> tuple[Record, list[str]]:
        """Returns validated record from ``submitted``, and the validation drop warnings.

        Raises:
            RecordError: node properties don't fit the ontology, or a value breaks a rule of its property.
        """
        graph, warnings = self.ontology.validate_node(submitted, cls)
        if not set(graph) - {JSONLD_TYPE, JSONLD_ID}:
            raise RecordError(
                "; ".join(warnings) or ERROR_NO_PROPERTIES.format(cls=cls)
            )
        self._check_identity(cls, graph)
        violation: str | None = self.ontology.find_rule_violation(graph, submitted)
        if violation is not None:
            raise RecordError(violation)
        links: tuple[Link, ...] = tuple(self.ontology.get_links(graph))
        return Record(
            record_id, cls, graph, submitted, self.ontology.version, links
        ), warnings

    def _check_identity(self, cls: str, graph: Mapping[str, Json]) -> None:
        """
        Raises:
            RecordError: ``cls`` has identity properties, but none holds a non-blank value in ``graph``.
        """
        identity_property_names: list[str] = (
            self.ontology.get_identity_property_names().get(cls, [])
        )
        if identity_property_names and not any(
            str(val).strip()
            for prop_name in identity_property_names
            if graph.get(prop_name) is not None
            for val in to_list(graph[prop_name])
        ):
            raise RecordError(
                ERROR_IDENTITY_REQUIRED.format(
                    cls=cls, prop_names=identity_property_names
                )
            )

    async def _write_record(
        self, record: Record, tx: Tx, expected_versions: Collection[str] | None
    ) -> None:
        """Locks, checks, saves and indexes the ``record``. All in ``tx``.

        Shared locks on parents. Do **NOT** lock other link targets, otherwise two items that link each other can
        deadlock. Parents limited by ``og:maxPerParent`` are locked: parent edges between classes have no cycles.
        """
        await self.check_version(record.id, expected_versions, tx)
        await self._check_class_is_kept(record, tx)
        for link in record.links:
            await self._check_link_target(record, link, tx)
        await self._check_max_per_parent(record, tx)
        await self._check_no_parent_loop(record, tx)
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

    async def _check_max_per_parent(self, record: Record, tx: Tx) -> None:
        """Counts the records of each parent ``record`` newly links to through a link limited by ``og:maxPerParent``.

        Locks the record, then its limited parents sorted by id: two writes to the same parent wait for each other, so
        the second one counts the first. Links the stored record already holds are not counted again.

        Raises:
            ParentLimitError: a parent already has as many records as its link allows.
        """
        limited: list[Link] = sorted(
            {
                link
                for link in record.links
                if self._get_max_per_parent(record.cls, link) is not None
            },
            key=lambda link: (link.target_id, link.property_name),
        )
        if not limited:
            return
        # a record created meanwhile was not locked: its links are counted like new ones
        stored: Record | None = None
        if await self.store.lock_record(record.id, tx) is not None:
            stored = await self.store.get_record(record.id, tx)
        kept: set[Link] = set(stored.links) if stored is not None else set()
        for link in limited:
            if link in kept:
                continue
            await self.store.lock_record(link.target_id, tx)
            linking: list[Record] = await self.store.get_linking_records(
                [link.target_id], tx
            )
            count: int = sum(
                1
                for rec in linking
                if rec.id != record.id and rec.cls == record.cls and link in rec.links
            )
            limit: int | None = self._get_max_per_parent(record.cls, link)
            if limit is not None and count >= limit:
                raise ParentLimitError(
                    ERROR_MAX_PER_PARENT.format(
                        target_id=link.target_id,
                        limit=limit,
                        cls=record.cls,
                        prop_name=link.property_name,
                    )
                )

    def _get_max_per_parent(self, cls: str, link: Link) -> int | None:
        return self.ontology.properties[cls, link.property_name].max_per_parent

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

    async def _check_no_parent_loop(self, record: Record, tx: Tx) -> None:
        """Walks up the parent links to ``record``'s own class (a tree, e.g. groups in groups).

        Locks the record and every ancestor on the way. Two writes that would close a loop together then wait for each
        other, and the database stops one of them (``ConflictError``); its retry sees the other's parent and refuses.

        Raises:
            RecordError: ``record`` would become its own ancestor.
        """
        prop_names: list[str] = sorted(
            name
            for name in self.ontology.get_parent_link_names(record.cls)
            if self.ontology.properties[record.cls, name].range == record.cls
        )
        if not prop_names:
            return
        await self.store.lock_record(record.id, tx)
        pending_ids: list[str] = _get_target_ids(record, prop_names)
        seen_ids: set[str] = set()
        while pending_ids:
            ancestor_id: str = pending_ids.pop()
            if ancestor_id == record.id:
                raise RecordError(
                    ERROR_PARENT_LOOP.format(
                        cls=record.cls, record_id=record.id, prop_names=prop_names
                    )
                )
            if ancestor_id in seen_ids:
                continue
            seen_ids.add(ancestor_id)
            await self.store.lock_record(ancestor_id, tx)
            ancestor: Record | None = await self.store.get_record(ancestor_id, tx)
            if ancestor is not None:
                pending_ids += _get_target_ids(ancestor, prop_names)

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


def _get_target_ids(record: Record, prop_names: list[str]) -> list[str]:
    """Returns the targets of ``record``'s links held by ``prop_names``."""
    return [link.target_id for link in record.links if link.property_name in prop_names]
