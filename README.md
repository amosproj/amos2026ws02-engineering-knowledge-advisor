# Engineering Knowledge Advisor

An application for organizing and accessing engineering knowledge, with the goal of helping users find relevant information across engineering documents and other knowledge sources.

The project uses a containerized web application architecture with a React frontend, a FastAPI backend, PostgreSQL with pgvector and pg_trgm, and S3-compatible object storage through MinIO. Docker Compose manages these services so that developers can run a consistent local environment without manually installing each runtime dependency.

## Table of Contents

- [Repository Structure](#repository-structure)
- [Quickstart](#quickstart)
- [Build & Run](#build--run)
- [Stop & Clean](#stop--clean)
- [Staging Deployment](#staging-deployment)
- [Manual Testing](#manual-testing)
- [Testing Guidelines](#testing-guidelines)
- [Software Bill of Materials](#software-bill-of-materials)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)
- [Technology Stack](#technology-stack)

## Repository Structure

```sh
engineering-knowledge-advisor/  # repo root
├── apps/
│   ├── api/                    # backend
│   └── web/                    # frontend
├── infra/                      # deployment, reverse proxy configs
├── scripts/                    # repo tooling scripts (SBOM, versions)
└── .env                        # see "Quickstart"
```

## Quickstart

**Prerequisites:** [uv](https://docs.astral.sh/uv/), Docker

### 1. Create your local environment file

The project uses a `.env` file for local configuration. Copy `.env.example` as `.env` in repository root.

`.env` holds configurations for both the frontend and backend. It **MUST NOT** be committed to Git.

[`VITE_*` variables](https://vite.dev/guide/env-and-mode):

- are **PUBLIC**: they are embedded in the browser bundle and readable by anyone
- **MUST NOT** hold secrets (e.g. passwords, API keys)
- **MUST** be added to `.env`, the `web` build `args` in `compose.yaml`, `apps/web/Dockerfile`, `apps/web/src/vite-env.d.ts` and `apps/web/src/utils/env.ts`
- are read at build time: rebuild the frontend after changing one

Frontend variables that are not exposed to the browser use the `WEB_` prefix (e.g. `WEB_API_PROXY_TARGET`, used only by the Vite dev server).

Use different, unique passwords for your local environment. Do not commit `.env` to Git or share real credentials in issues, screenshots, or messages.

Keep `.env.example` updated whenever required environment variables change, but use placeholder values in that file.

### 2. Initialize Python venv and install the pre-commit hook

This will install the pre-commit Git hook and auto-init venv based on `apps/api/pyproject.toml`

From the repository root, run:

```sh
uv run --project apps/api pre-commit install  # will also run uv sync
```

(optional) manual test-run:

```sh
uv run --project apps/api pre-commit
```

To uninstall the hook:

```sh
uv run --project apps/api pre-commit uninstall
```

## Build & Run

```sh
docker compose up --build
```

## Stop & Clean

```sh
docker compose <COMMAND>
```

` <COMMAND>`:
- `down` - stops, removes containers and networks, but retains volumes
- `down -v` - **Warning:** also deletes volumes
- `stop` - stops services, retains containers and volumes
- `start` - restarts services

## Staging Deployment

The deployment workflow builds and pushes the frontend and API Docker images to the `ekadvisor` Docker Hub account, using the following repositories:

- `engineering-knowledge-advisor-web`
- `engineering-knowledge-advisor-api`

### Automatic Deployment of Updated Images

A service running on the VPS checks the Docker Hub repositories for new images every two minutes. When an updated image is detected, the service automatically pulls the latest image and restarts the corresponding application service.

**Note:** Automatic updates apply only to the frontend and API images. PostgreSQL, MinIO and other components are not updated automatically.

### Rolling Back a Deployment

If a deployment needs to be rolled back, there are two options:

1. **Create a corrective release:** Build and deploy a new release containing the required fixes.
2. **Revert to a previous image:** Log in to the team's Docker Hub account and retag a previously deployed image as `latest`. The VPS service will detect the updated tag and pull the corresponding image during its next check.

## Manual Testing

### Frontend

http://localhost:8080

- `WEB_PROFILE=dev` - frontend runs through Vite, source changes are picked up automatically.
- `WEB_PROFILE=prod` - built frontend served through Nginx.

### API health check

http://localhost:8080/api/health/live

`200 OK` confirms that Nginx can forward the health-check request to FastAPI.

### Work locally without Docker

The frontend can also be run independently using Node.js and npm:

```sh
cd apps/web
npm ci
npm run dev
```

Frontend tests use [Vitest](https://vitest.dev) and uses (`*.test.ts`) files. CI (`.github/workflows/web-tests.yaml`) runs ESLint, Prettier, TypeScript and Vitest on every pull request:

```sh
cd apps/web
npm test             # run once
npm run test:watch   # re-run on change
```

The API can be run locally with uv installed:

```sh
uv sync --project apps/api
uv run --project apps/api uvicorn main:app --reload
```

The local API runs at `http://127.0.0.1:8000`. Local execution requires any external services to be configured and reachable.

## Testing Guidelines

Detailed instructions on automated tests, manual testing requirements, and available test environments can be found in [testing.md](Documentation/testing.md).

## Software Bill of Materials

CycloneDX SBOMs for the API and frontend are generated from the lockfiles, enforced by a pre-commit hook and checked in CI. Setup, regeneration, and tool version requirements are described in [Documentation/sbom/README.md](Documentation/sbom/README.md).

## Troubleshooting

### Image pull fails

If a public image is unavailable or access is denied, inspect the image name and tag in `compose.yaml`.

A login cannot fix an invalid or removed image reference. To login to Docker Hub:

```sh
docker login
docker compose pull
```

### A service doesn't start / health check fail

Inspect container logs:

```sh
docker compose ps                # list running containers, services
docker compose logs --tail 100   # list last 100 logs
docker compose logs web          # list frontend logs
docker compose logs api -f       # list backend logs (following)
```

### A port is already in use

If host port `8080` is occupied, change the published port in `compose.yaml`. For example:

```yaml
ports:
  - "127.0.0.1:8081:80"
```

The frontend will then be available at `http://localhost:8081`.

## Security Notes

- **NEVER** commit `.env`, credentials, access tokens, or other secrets.
- Use unique local development credentials.
- Do **NOT** expose PostgreSQL or MinIO administrative interfaces publicly.
- Keep Docker Desktop, Docker Engine, and container images updated.
- Use stronger secret-management practices for shared environments and production deployments.
- Treat local container configuration as a development setup until production security, storage initialization, backups, and deployment requirements have been reviewed.

## Technology Stack

| Component                    | Technology               | Purpose                                       |
| ---------------------------- | ------------------------ | --------------------------------------------- |
| Frontend                     | React, TypeScript, Vite  | Web user interface                            |
| Web server                   | Nginx                    | Serves the frontend and forwards API requests |
| Backend                      | Python, FastAPI, Uvicorn | REST API                                      |
| Database                     | PostgreSQL 16            | Persistent relational data                    |
| Vector search                | pgvector                 | Foundation for vector similarity search       |
| Object storage               | MinIO                    | Local S3-compatible document storage          |
| Containerization             | Docker                   | Builds and runs application containers        |
| Orchestration                | Docker Compose           | Configures and connects the services          |
| Python dependency management | uv                       | Manages backend dependencies and the lockfile |
| CAD file parsing             | cadquery-ocp             | Parses STEP files & extracts structure        |
