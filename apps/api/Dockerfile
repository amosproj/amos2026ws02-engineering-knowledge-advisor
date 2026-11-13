ARG API_PROFILE=prod

# Use the official Python image
FROM python:3.13-slim as api-base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

# Install system dependencies required by OpenCASCADE/OCP (CAD parser)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libfontconfig1 \
    libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user that owns /app, files are written as this user so no chown layer copies them
RUN useradd --create-home --uid 1000 appuser \
    && mkdir /app && chown appuser:appuser /app
USER appuser

# Set the application directory
WORKDIR /app

# Configure uv for predictable container installs
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Copy project metadata and README
COPY --chown=appuser:appuser pyproject.toml uv.lock README.md ./

# Install dependencies using the lockfile, uv's cache stays in build cache and out of image
RUN --mount=type=cache,target=/home/appuser/.cache/uv,uid=1000,gid=1000 \
    uv sync --frozen --no-dev --no-install-project

# Copy application source and install the project
COPY --chown=appuser:appuser src ./src
RUN --mount=type=cache,target=/home/appuser/.cache/uv,uid=1000,gid=1000 \
    uv sync --frozen --no-dev

# OG-RAG ontology (API_OGRAG_ONTOLOGY_PATH) and the database migrations
# (run migrations before starting a new version: uv run --no-sync alembic upgrade head)
COPY --chown=appuser:appuser ontology_v0.jsonld alembic.ini ./
COPY --chown=appuser:appuser migrations ./migrations

EXPOSE 8000

FROM api-base AS dev

ARG API_PROFILE
RUN test "$API_PROFILE" = "dev"

CMD ["uv", "run", "--no-sync", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM api-base AS prod

ARG API_PROFILE
RUN test "$API_PROFILE" = "prod"

CMD ["uv", "run", "--no-sync", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
