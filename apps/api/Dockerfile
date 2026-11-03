ARG API_PROFILE=prod

# Use the official Python image
FROM python:3.13-slim as api-base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

# Set the application directory
WORKDIR /app

# Configure uv for predictable container installs
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Copy project metadata and README
COPY pyproject.toml uv.lock README.md ./

# Install dependencies using the lockfile
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source and install the project
COPY src ./src
RUN uv sync --frozen --no-dev

# OG-RAG ontology (API_OGRAG_ONTOLOGY_PATH) and the database migrations
# (run migrations before starting a new version: uv run --no-sync alembic upgrade head)
COPY ontology_v0.jsonld alembic.ini ./
COPY migrations ./migrations

# Run as a non-root user
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

FROM api-base AS dev

ARG API_PROFILE
RUN test "$API_PROFILE" = "dev"

CMD ["uv", "run", "--no-sync", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM api-base AS prod

ARG API_PROFILE
RUN test "$API_PROFILE" = "prod"

CMD ["uv", "run", "--no-sync", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
