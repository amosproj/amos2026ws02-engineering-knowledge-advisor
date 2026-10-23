from fastapi import FastAPI

app = FastAPI(
    title="Engineering Knowledge Advisor API",
    version="0.1.0",
)


@app.get("/api/health/live", tags=["health"])
def health_check() -> dict[str, str]:
    """Confirm that the API process is running."""
    return {"status": "ok"}
