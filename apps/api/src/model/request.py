from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, RootModel
from pydantic.alias_generators import to_camel

from services import JsonObject
from services.ograg.ontology import JSONLD_ID, JSONLD_TYPE

FILE_MAX_SIZE: int = 5 * 1024 * 1024 * 1024  # 5 GiB


class CamelModel(BaseModel):
    """Model with camelCase JSON keys."""

    model_config = ConfigDict(
        alias_generator=to_camel, validate_by_name=True, serialize_by_alias=True
    )


class RecordNode(BaseModel):
    """JSON-LD node of a record class. Properties as defined by the ontology. Links hold target ids.
    Every property besides ``@type`` and ``@id`` is kept as sent.
    """

    model_config = ConfigDict(extra="allow")

    type: str | None = Field(
        default=None,
        alias=JSONLD_TYPE,
        description="Record class. Defaults to anchor class.",
    )
    id: str | None = Field(
        default=None,
        alias=JSONLD_ID,
        description="Record id. PUT specifies it in the URL.",
    )

    def to_node(self) -> JsonObject:
        """Returns the node as sent."""
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")


class RecordChanges(RootModel[JsonObject]):
    """JSON Merge Patch (RFC 7396) of a record. Class properties -> new value."""


class FileToUpload(CamelModel):
    """Body of ``POST /records/{id}/upload-form``."""

    size: Annotated[int, Field(ge=1, le=FILE_MAX_SIZE, description="Size in bytes.")]
