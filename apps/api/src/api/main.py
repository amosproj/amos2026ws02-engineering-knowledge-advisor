from fastapi import FastAPI

from api.todos import router as todos_router

app = FastAPI(
    title="Engineering Knowledge Advisor API",
    version="0.1.0",
)

app.include_router(todos_router)


@app.get("/api/health/live", tags=["health"])
def health_check() -> dict[str, str]:
    """Confirm that the API process is running."""
    return {"status": "ok"}
