
# Use the official Python image
FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /uvx /bin/

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

# Run as a non-root user
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]