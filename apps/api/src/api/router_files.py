"""File uploads of file records, and walking the parent links: a record's tree below it and its ancestors above it."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response, status

from api.router_builder import ApiRouterBuilder
from api.router_records import (
    NOT_FOUND,
    RESPONSE_DETAIL_404,
    Catalog,
    RecordId,
    Session,
    to_file_upload,
    to_node,
)
from model import (
    NO_FILE,
    FileStatus,
    FileToUpload,
    FileUpload,
    RecordAncestors,
    RecordTree,
    UploadForm,
)
from model.problem import Problem, ProblemResponse
from services.catalog import PresignedForm, TreeNode, UploadMismatch
from services.catalog.service import FILE_MISMATCH
from services.uploads import Upload

RESPONSE_DETAIL_200_GET_TREE: str = (
    "Record with every record below it. File records carry status and upload metadata."
)
RESPONSE_DETAIL_200_GET_ANCESTORS: str = "Record with its parents up to the top."
RESPONSE_DETAIL_200_UPLOAD_FORM: str = "Form to upload the file with."
RESPONSE_DETAIL_202_COMPLETE: str = "File is queued for processing, or processed."
RESPONSE_DETAIL_409_UPLOAD_FORM: str = (
    "File is being processed, already ready, or the worker holds it."
)
RESPONSE_DETAIL_409_COMPLETE: str = "Upload not found and file does not match, or import failed, or the file is being processed."
RESPONSE_DETAIL_422_NO_FILE: str = (
    "Request validation failed, or the record's class carries no file."
)
RESPONSE_DETAIL_503: str = "File storage cannot be reached. Please try again."
ERROR_FILE_MISMATCH: str = "Uploaded file does not match the announced size."

v1_files_router: APIRouter = (
    ApiRouterBuilder().version("v1").add_tags(["records"]).build()
)


@v1_files_router.get(
    "/records/{recordId}/tree",
    response_model_exclude_unset=True,
    responses={
        200: {"model": RecordTree, "description": RESPONSE_DETAIL_200_GET_TREE},
        **NOT_FOUND,
    },
)
async def get_record_tree(
    record_id: RecordId,
    catalog: Catalog,
    session: Session,
    depth: Annotated[
        int | None,
        Query(ge=1, description="Levels below the record. All if None."),
    ] = None,
) -> RecordTree:
    """Returns record with every record linking to it through a parent link."""
    return _to_tree(await catalog.get_tree(session, record_id, depth))


@v1_files_router.get(
    "/records/{recordId}/ancestors",
    response_model_exclude_unset=True,
    responses={
        200: {
            "model": RecordAncestors,
            "description": RESPONSE_DETAIL_200_GET_ANCESTORS,
        },
        **NOT_FOUND,
    },
)
async def get_record_ancestors(
    record_id: RecordId,
    catalog: Catalog,
    session: Session,
    depth: Annotated[
        int | None,
        Query(ge=1, description="Levels above the record. All if None."),
    ] = None,
) -> RecordAncestors:
    """Returns record with its parents, their parents and so on."""
    return _to_ancestors(await catalog.get_ancestors(session, record_id, depth))


@v1_files_router.post(
    "/records/{recordId}/upload-form",
    responses={
        200: {"model": UploadForm, "description": RESPONSE_DETAIL_200_UPLOAD_FORM},
        404: {"model": Problem, "description": RESPONSE_DETAIL_404},
        409: {"model": Problem, "description": RESPONSE_DETAIL_409_UPLOAD_FORM},
        422: {"model": Problem, "description": RESPONSE_DETAIL_422_NO_FILE},
    },
)
async def post_upload_form(
    record_id: RecordId, body: FileToUpload, catalog: Catalog, session: Session
) -> UploadForm:
    """Returns form to upload the file record's file with (object storage).

    Re-upload to replace running or failed upload. Call ``POST /records/{id}/complete`` after completed upload.
    """
    form: PresignedForm = await catalog.create_upload_form(
        session, record_id, body.size
    )
    return UploadForm(url=form.url, fields=form.fields)


@v1_files_router.post(
    "/records/{recordId}/complete",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=FileUpload,
    responses={
        202: {"model": FileUpload, "description": RESPONSE_DETAIL_202_COMPLETE},
        404: {"model": Problem, "description": RESPONSE_DETAIL_404},
        409: {"model": Problem, "description": RESPONSE_DETAIL_409_COMPLETE},
        422: {"model": Problem, "description": RESPONSE_DETAIL_422_NO_FILE},
        503: {"model": Problem, "description": RESPONSE_DETAIL_503},
    },
)
async def complete_upload(
    record_id: RecordId,
    request: Request,
    catalog: Catalog,
    session: Session,
    background_tasks: BackgroundTasks,
) -> FileUpload | Response:
    """Confirms file upload and queues it for processing."""
    result: Upload | UploadMismatch = await catalog.complete_upload(session, record_id)
    if isinstance(result, UploadMismatch):
        background_tasks.add_task(catalog.delete_source_folders, [result.source_key])
        # returned, raising would roll back
        return ProblemResponse.from_status(
            409,
            ERROR_FILE_MISMATCH,
            error_code=FILE_MISMATCH,
            instance=request.url.path,
        )
    return to_file_upload(result)


def _to_tree(node: TreeNode) -> RecordTree:
    tree = RecordTree(
        record=to_node(node.record),
        version=node.record.version,
        children=[_to_tree(child) for child in node.linked],
    )
    if node.has_status:
        tree.status = _get_file_status(node)
    if node.file:
        tree.upload = _get_file_upload(node)
    return tree


def _to_ancestors(node: TreeNode) -> RecordAncestors:
    ancestors = RecordAncestors(
        record=to_node(node.record),
        version=node.record.version,
        parents=[_to_ancestors(parent) for parent in node.linked],
    )
    if node.has_status:
        ancestors.status = _get_file_status(node)
    if node.file:
        ancestors.upload = _get_file_upload(node)
    return ancestors


def _get_file_status(node: TreeNode) -> FileStatus:
    return NO_FILE if node.status is None else node.status


def _get_file_upload(node: TreeNode) -> FileUpload | None:
    return None if node.upload is None else to_file_upload(node.upload)
