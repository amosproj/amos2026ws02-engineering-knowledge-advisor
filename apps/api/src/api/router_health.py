from fastapi import APIRouter

from api.router_builder import ApiRouterBuilder

health_router: APIRouter = ApiRouterBuilder().tags(["health"]).build()


@health_router.get(
    "/health/live",
    responses={
        200: {"model": dict[str, str], "description": "Successful response"},
    },
)
def health() -> dict[str, str]:
    """Confirm that the API process is running."""
    return {"status": "ok"}
