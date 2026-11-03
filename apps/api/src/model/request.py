from pydantic import BaseModel, ConfigDict, Field

from services import JsonObject
from services.ograg.ontology import JSONLD_ID, JSONLD_TYPE


class TestRequest(BaseModel):
    ping: int


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
