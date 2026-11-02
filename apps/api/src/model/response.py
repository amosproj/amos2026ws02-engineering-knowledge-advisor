from pydantic import BaseModel, RootModel

from model.request import RecordNode


class TestResponse(BaseModel):
    pong: int


class RecordWritten(BaseModel):
    """Response of ``PUT /records/{id}``.

    Attributes:
        warnings: validation drops
    """

    id: str
    warnings: list[str]


class RecordsDeleted(BaseModel):
    """Response of ``DELETE /records/{id}``.

    Attributes:
        deleted_ids: id of deleted record + ids of deleted orphans
        marked_ids: ids of records that lost their last parent link and were marked for review
    """

    deleted_ids: list[str]
    marked_ids: list[str]


class RecordToReview(BaseModel):
    """A marked record."""

    id: str
    review: str
    record: RecordNode


class Records(RootModel[dict[str, RecordNode]]):
    """Response of ``GET /records``. Wraps map: record id -> validated node"""
