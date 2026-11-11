"""Records of any record class, with the upload state and the stored files of the file records.

Every method runs in the caller's session and does not commit. Objects are deleted only after
the commit: the methods that delete return the source keys to pass to ``delete_source_folders``.
"""

from __future__ import annotations

import asyncio
from collections.abc import (
    AsyncGenerator,
    Awaitable,
    Callable,
    Collection,
    Iterable,
    Mapping,
)
from contextlib import asynccontextmanager
from dataclasses import dataclass

from services import Json, Record, Tx
from services.catalog import records
from services.catalog.errors import (
    BusyError,
    ImportFailedError,
    UploadExistsError,
    UploadNotFoundError,
)
from services.catalog.files import get_folder, get_source_key
from services.catalog.records import Fields
from services.object_storage import ObjectStorage
from services.ograg.service import DeleteResult, OgRagService, RecordError
from services.uploads import LockTimeoutError, Upload, UploadStatus, UploadStore

FILE_MISMATCH: str = "file_mismatch"
# most urgent first
STATUS_PRIORITY: tuple[UploadStatus, ...] = (
    UploadStatus.UPLOADING,
    UploadStatus.PROCESSING,
    UploadStatus.FAILED,
    UploadStatus.READY,
)

ERROR_NO_FILE: str = "a {cls} carries no file"


@dataclass(frozen=True)
class UploadMismatch:
    """The uploaded file does not have the announced size. The CAD file is failed, its object is to delete."""

    source_key: str


@dataclass(frozen=True)
class PresignedForm:
    """Form the client posts the file with: ``fields``, then the file as ``file``, to ``url``."""

    url: str
    fields: dict[str, str]


@dataclass(frozen=True)
class CreatedRecord:
    """Result of ``CatalogService.create_record``.

    Attributes:
        record: the stored record.
        warnings: validation drops.
    """

    record: Record
    warnings: list[str]


@dataclass(frozen=True)
class DeletedRecords:
    """Result of ``CatalogService.delete_record``.

    Attributes:
        deleted_ids: the record and every record deleted with it.
        marked_ids: records that lost their last parent link and were marked for review.
        source_keys: files to delete after the commit (``delete_source_folders``).
    """

    deleted_ids: list[str]
    marked_ids: list[str]
    source_keys: list[str]


@dataclass(frozen=True)
class TreeNode:
    """A record with the records one parent link further, nested (``get_tree``, ``get_ancestors``).

    Attributes:
        record: the record.
        file: the record's class carries a file (``og:file``).
        upload: upload state of a file record, ``None`` without upload or for other records.
        has_status: ``CatalogService.has_status``.
        status: upload status, ``None`` if none.
        linked: sorted by id: the records whose parent links point to this one (``get_tree``), or the records this
            one's parent links point to (``get_ancestors``).
    """

    record: Record
    file: bool
    upload: Upload | None
    has_status: bool
    status: UploadStatus | None
    linked: list[TreeNode]


@dataclass(frozen=True)
class UploadStates:
    """Result of ``CatalogService.get_upload_states``.

    Attributes:
        uploads: file id -> upload.
        statuses: record id -> upload status.
    """

    uploads: dict[str, Upload]
    statuses: dict[str, UploadStatus | None]


type GetLinked = Callable[[list[Record]], Awaitable[dict[str, list[Record]]]]


def get_files_status(statuses: Iterable[UploadStatus]) -> UploadStatus | None:
    """The most urgent of ``statuses``, ``None`` without any."""
    ranks: list[int] = [STATUS_PRIORITY.index(stat) for stat in statuses]
    return STATUS_PRIORITY[min(ranks)] if ranks else None


class CatalogService:
    def __init__(
        self, ograg: OgRagService, uploads: UploadStore, storage: ObjectStorage
    ) -> None:
        self.ograg: OgRagService = ograg
        self.uploads: UploadStore = uploads
        self.storage: ObjectStorage = storage

    async def get_record(
        self, session: Tx, record_id: str, cls: str | None = None
    ) -> Record:
        """The record ``record_id`` (of class ``cls``, if given), else ``NotFoundError``."""
        return await records.get_record(self.ograg, session, record_id, cls)

    async def get_records(
        self, session: Tx, cls: str | None = None, parent_id: str | None = None
    ) -> list[Record]:
        """All records, sorted by id.

        Args:
            session: transaction.
            cls: only records of this class.
            parent_id: only records whose parent links point to this record, file records included.
        """
        if parent_id is not None:
            children: list[Record] = await records.get_children(
                self.ograg, session, [parent_id]
            )
            return [rec for rec in children if cls is None or rec.cls == cls]
        if cls is None:
            return await self.ograg.store.get_all_records(session)
        return await self.ograg.store.get_records_by_class(cls, session)

    def is_file_record(self, record: Record) -> bool:
        """Whether ``record``'s class carries a file (``og:file``)."""
        return record.cls in self.ograg.ontology.file_classes

    def has_status(self, record: Record) -> bool:
        """Whether ``record`` carries a file or file records can point to its class."""
        return (
            self.is_file_record(record)
            or record.cls in self.ograg.ontology.get_file_parent_classes()
        )

    async def get_status(self, session: Tx, record_id: str) -> UploadStatus | None:
        """The most urgent upload status of the record's files (``get_upload_states``), ``None`` without upload."""
        record: Record = await self.get_record(session, record_id)
        states: UploadStates = await self.get_upload_states(session, [record])
        return states.statuses.get(record_id)

    async def get_upload_states(self, session: Tx, found: list[Record]) -> UploadStates:
        """Returns the uploads and the upload status per record of ``found``.

        File record: its own status. Other records: the most urgent of the file records linking straight to them.
        """
        parent_ids: list[str] = [
            rec.id
            for rec in found
            if self.has_status(rec) and not self.is_file_record(rec)
        ]
        children: list[Record] = await records.get_children(
            self.ograg, session, parent_ids
        )
        file_records: dict[str, Record] = {
            rec.id: rec for rec in found + children if self.is_file_record(rec)
        }
        uploads: dict[str, Upload] = await self.uploads.get_uploads(
            list(file_records), session
        )
        statuses_by_id: dict[str, list[UploadStatus]] = {}
        for file_id, upload in uploads.items():
            owner_ids: list[str] = [
                file_id,
                *self._get_parent_ids(file_records[file_id], parent_ids),
            ]
            for owner_id in owner_ids:
                statuses_by_id.setdefault(owner_id, []).append(upload.status)
        return UploadStates(
            uploads=uploads,
            statuses={
                rec_id: get_files_status(statuses)
                for rec_id, statuses in statuses_by_id.items()
            },
        )

    async def get_children_by_parent_id(
        self, session: Tx, parents: list[Record]
    ) -> dict[str, list[Record]]:
        """Parent id -> the records whose parent links point to it, sorted by id. One read for all ``parents``."""
        parent_ids: list[str] = [rec.id for rec in parents]
        children_by_parent_id: dict[str, list[Record]] = {}
        for child in await records.get_children(self.ograg, session, parent_ids):
            for parent_id in self._get_parent_ids(child, parent_ids):
                children_by_parent_id.setdefault(parent_id, []).append(child)
        return children_by_parent_id

    async def get_upload(self, session: Tx, file_id: str) -> Upload | None:
        """Returns the upload of file record ``file_id``, or ``None``."""
        uploads: dict[str, Upload] = await self.uploads.get_uploads([file_id], session)
        return uploads.get(file_id)

    async def get_tree(
        self, session: Tx, record_id: str, depth: int | None = None
    ) -> TreeNode:
        """The record with every record below it through parent links, file records with their upload.

        Reads one level per query. A record with several parents appears under each; a record never appears below
        itself.

        Args:
            session: transaction.
            record_id: the top of the tree.
            depth: levels below the record, ``None`` for all.

        Raises:
            NotFoundError: no record ``record_id``.
        """
        return await self._walk(
            session,
            record_id,
            depth,
            lambda parents: self.get_children_by_parent_id(session, parents),
        )

    async def get_ancestors(
        self, session: Tx, record_id: str, depth: int | None = None
    ) -> TreeNode:
        """The record with its parents, their parents and so on up to the top, e.g. the machine.

        Reads one level per query. A record with several parents lists each; a record never appears above itself.

        Args:
            session: transaction.
            record_id: the record to start from.
            depth: levels above the record, ``None`` for all.

        Raises:
            NotFoundError: no record ``record_id``.
        """

        async def get_parents_by_child_id(
            children: list[Record],
        ) -> dict[str, list[Record]]:
            parent_ids_by_child_id: dict[str, list[str]] = {
                rec.id: self._get_parent_ids(rec) for rec in children
            }
            wanted_ids: list[str] = sorted(
                {
                    parent_id
                    for ids in parent_ids_by_child_id.values()
                    for parent_id in ids
                }
            )
            loaded: dict[str, Record] = {
                rec.id: rec
                for rec in await self.ograg.store.get_records(wanted_ids, session)
            }
            return {
                child_id: [
                    loaded[parent_id]
                    for parent_id in sorted(ids)
                    if parent_id in loaded
                ]
                for child_id, ids in parent_ids_by_child_id.items()
            }

        return await self._walk(session, record_id, depth, get_parents_by_child_id)

    async def create_record(
        self, session: Tx, node: Mapping[str, Json]
    ) -> CreatedRecord:
        """Stores ``node`` as a new record with a generated id. A file record starts without upload.

        Raises:
            RecordError: ``node`` is invalid.
        """
        record_id, warnings = await records.create_record(self.ograg, session, node)
        return CreatedRecord(
            record=await self.get_record(session, record_id), warnings=warnings
        )

    async def update_record(
        self,
        session: Tx,
        record_id: str,
        changes: Fields,
        expected_versions: Collection[str] | None = None,
    ) -> list[str]:
        """Changes only the fields given in ``changes`` (``records.update_record``). Returns the warnings."""
        return await records.update_record(
            self.ograg, session, record_id, changes, expected_versions
        )

    async def delete_record(
        self,
        session: Tx,
        record_id: str,
        delete_orphans: bool = False,
        expected_versions: Collection[str] | None = None,
    ) -> DeletedRecords:
        """Deletes the record and the records deleted with it (``og:deleteWithParent``), children first.

        Records that lose their last parent link otherwise are marked for review, or deleted if
        ``delete_orphans`` is ``True``.

        Raises:
            NotFoundError: no record ``record_id``.
            BusyError: the worker holds one of the files.
            StaleVersionError: record has none of ``expected_versions``.
        """
        async with self._busy_after_lock_timeout(session):
            # locked before their files are listed, so no file can be added meanwhile
            tree: list[Record] = await records.lock_tree(self.ograg, session, record_id)
            await self.ograg.check_version(record_id, expected_versions, session)
            uploads: dict[str, Upload] = await self.uploads.get_uploads(
                [rec.id for rec in tree if self.is_file_record(rec)], session
            )
            result: DeleteResult = await records.delete_tree(
                self.ograg, session, tree, delete_orphans
            )
        return DeletedRecords(
            deleted_ids=result.deleted_ids,
            marked_ids=result.marked_ids,
            source_keys=[upload.source_key for upload in uploads.values()],
        )

    async def create_upload_form(
        self, session: Tx, file_id: str, size_bytes: int
    ) -> PresignedForm:
        """Registers the upload of the file record's file and returns the form to upload it with.

        Replaces an upload that is still uploading or has failed.

        Raises:
            NotFoundError: no record ``file_id``.
            RecordError: the record's class carries no file.
            UploadExistsError: the file is being processed or is ready.
            BusyError: the worker holds the file.
        """
        async with self._busy_after_lock_timeout(session):
            # a deletion of the record waits, so no upload is left without its record
            await self.ograg.store.lock_record(file_id, session)
            await self._get_file_record(session, file_id)
            source_key: str = get_source_key(file_id)
            started: Upload | None = await self.uploads.start_upload(
                file_id, source_key, size_bytes, session
            )
        if started is None:
            raise UploadExistsError()
        url, fields = self.storage.create_upload_form(source_key, size_bytes)
        return PresignedForm(url=url, fields=fields)

    async def complete_upload(
        self, session: Tx, file_id: str
    ) -> Upload | UploadMismatch:
        """Queues the uploaded file for processing. Returns the current state once it left uploading.

        Raises:
            NotFoundError: no record ``file_id``.
            RecordError: the record's class carries no file.
            UploadNotFoundError: no upload form was requested, or the file has not been uploaded.
            ImportFailedError: the import failed earlier.
            BusyError: the worker holds the file.
        """
        await self._get_file_record(session, file_id)
        async with self._busy_after_lock_timeout(session):
            upload: Upload = await self._get_upload(session, file_id)
            if upload.status != UploadStatus.UPLOADING:
                return _to_completed(upload)

            size: int | None = await asyncio.to_thread(
                self.storage.get_object_size, upload.source_key
            )
            if size is None:
                # a concurrent request may have completed or failed the upload meanwhile
                current: Upload = await self._get_upload(session, file_id)
                if current.status != UploadStatus.UPLOADING:
                    return _to_completed(current)
                raise UploadNotFoundError()

            mismatch: bool = size != upload.size_bytes
            changed: Upload | None = await self.uploads.finish_upload(
                file_id, FILE_MISMATCH if mismatch else None, session
            )

        if changed is None:
            return _to_completed(await self._get_upload(session, file_id))
        if mismatch:
            return UploadMismatch(upload.source_key)
        return changed

    def delete_source_folders(self, source_keys: list[str]) -> None:
        """Deletes the folder of each source key. Blocking, call it after the commit."""
        self.storage.delete_folders_quietly([get_folder(key) for key in source_keys])

    def _get_parent_ids(
        self, record: Record, candidate_ids: list[str] | None = None
    ) -> list[str]:
        """The ids ``record``'s parent links point to, each once; only those of ``candidate_ids`` if given."""
        parent_link_names: set[str] = self.ograg.ontology.get_parent_link_names(
            record.cls
        )
        candidates: set[str] | None = (
            None if candidate_ids is None else set(candidate_ids)
        )
        return list(
            dict.fromkeys(
                link.target_id
                for link in record.links
                if link.property_name in parent_link_names
                and (candidates is None or link.target_id in candidates)
            )
        )

    async def _walk(
        self, session: Tx, record_id: str, depth: int | None, get_linked: GetLinked
    ) -> TreeNode:
        """Follows ``get_linked`` from the record one level per call, then nests what it found.

        Every record is followed once; a record never appears below itself, so old data with a loop ends.

        Args:
            session: transaction.
            record_id: where to start.
            depth: levels to follow, ``None`` for all.
            get_linked: records of one level -> record id -> its linked records.

        Raises:
            NotFoundError: no record ``record_id``.
        """
        start: Record = await self.get_record(session, record_id)
        linked_by_id: dict[str, list[Record]] = {}
        found: dict[str, Record] = {start.id: start}
        level_records: list[Record] = [start]
        level: int = 0
        while level_records and (depth is None or level < depth):
            next_records: list[Record] = []
            for linking_id, linked in (await get_linked(level_records)).items():
                linked_by_id[linking_id] = linked
                for rec in linked:
                    if rec.id not in found:
                        found[rec.id] = rec
                        next_records.append(rec)
            level_records = next_records
            level += 1

        states: UploadStates = await self.get_upload_states(
            session, list(found.values())
        )

        def build(
            record: Record, levels_left: int | None, path_ids: set[str]
        ) -> TreeNode:
            linked_nodes: list[TreeNode] = []
            if levels_left != 0:
                linked_nodes = [
                    build(
                        rec,
                        None if levels_left is None else levels_left - 1,
                        path_ids | {rec.id},
                    )
                    for rec in linked_by_id.get(record.id, [])
                    if rec.id not in path_ids
                ]
            return TreeNode(
                record=record,
                file=self.is_file_record(record),
                upload=states.uploads.get(record.id),
                has_status=self.has_status(record),
                status=states.statuses.get(record.id),
                linked=linked_nodes,
            )

        return build(start, depth, {start.id})

    async def _get_file_record(self, session: Tx, file_id: str) -> Record:
        """
        Raises:
            NotFoundError: no record ``file_id``.
            RecordError: the record's class carries no file.
        """
        record: Record = await self.get_record(session, file_id)
        if not self.is_file_record(record):
            raise RecordError(ERROR_NO_FILE.format(cls=record.cls))
        return record

    async def _get_upload(self, session: Tx, file_id: str) -> Upload:
        """
        Raises:
            UploadNotFoundError: the file record has no upload.
        """
        upload: Upload | None = await self.get_upload(session, file_id)
        if upload is None:
            raise UploadNotFoundError()
        return upload

    @asynccontextmanager
    async def _busy_after_lock_timeout(self, session: Tx) -> AsyncGenerator[None]:
        """Waits only briefly for a locked row, then raises ``BusyError`` instead of waiting for the worker."""
        try:
            async with self.uploads.limit_lock_wait(session):
                yield
        except LockTimeoutError as exc:
            raise BusyError() from exc


def _to_completed(upload: Upload) -> Upload:
    if upload.status == UploadStatus.FAILED:
        raise ImportFailedError(upload.error_code)
    return upload
