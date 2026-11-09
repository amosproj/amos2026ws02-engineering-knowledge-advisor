"""What clients need to know about the ontology's classes and properties."""

from fastapi import APIRouter

from api.router_builder import ApiRouterBuilder
from api.router_records import Service
from model import OntologyClass, OntologyDescription
from services.ograg.ontology import Ontology

RESPONSE_DETAIL_200_GET: str = (
    "Every class of the ontology with its properties and annotations."
)

v1_ontology_router: APIRouter = (
    ApiRouterBuilder().version("v1").add_tags(["ontology"]).build()
)


@v1_ontology_router.get(
    "/ontology",
    responses={
        200: {"model": OntologyDescription, "description": RESPONSE_DETAIL_200_GET},
    },
)
async def get_ontology(service: Service) -> OntologyDescription:
    """Returns loaded ontology with every class and property."""
    onto: Ontology = service.ontology
    return OntologyDescription(
        version=onto.version,
        classes={
            cls: OntologyClass.model_validate(description, from_attributes=True)
            for cls, description in onto.describe().items()
        },
    )
