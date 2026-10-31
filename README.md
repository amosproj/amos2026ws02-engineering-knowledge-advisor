# Engineering Knowledge Advisor

An application for organizing and accessing engineering knowledge, with the goal of helping users find relevant information across engineering documents and other knowledge sources.

The project uses a containerized web application architecture with a React frontend, a FastAPI backend, PostgreSQL with pgvector, and S3-compatible object storage through MinIO.

## Table of Contents

- [Project Overview](#project-overview)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Running the Application](#running-the-application)
- [Stopping the Application](#stopping-the-application)
- [Testing the Services](#testing-the-services)
- [Running the Tests](#running-the-tests)
- [Working on a Single App](#working-on-a-single-app)
- [Docker Operations](#docker-operations)
- [Software Bill of Materials](#software-bill-of-materials)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)
- [Project Status](#project-status)
- [Command Reference](#command-reference)

## Project Overview

The Engineering Knowledge Advisor is being developed as a web application for working with engineering knowledge.

The architecture separates the frontend, API, database, and object storage into individual services. Docker Compose manages these services so that developers can run a consistent local environment without manually installing each service.

The repository is a monorepo driven from a root `package.json`: every common task (install, run, stop, test) is a single `npm run` command executed from the repository root.

The current setup provides the initial application skeleton and containerized infrastructure. The API health endpoint is implemented, while document processing, database models, document uploads, and vector search remain future development tasks.

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
| Task runner                  | npm, concurrently        | Root scripts that run the apps together       |

## Repository Structure

```text
engineering-knowledge-advisor/
├── apps/
│   ├── api/
│   │   ├── src/
│   │   │   ├── api/
│   │   │   ├── config/
│   │   │   ├── handler/
│   │   │   ├── logger/
│   │   │   ├── model/
│   │   │   └── main.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── .dockerignore
│   │   ├── pyproject.toml
│   │   ├── uv.lock
│   │   └── README.md
│   └── web/
│       ├── src/
│       ├── public/
│       ├── Dockerfile
│       ├── package.json
│       └── package-lock.json
├── infra/
│   ├── nginx/
│   │   └── default.conf
│   └── postgres/
│       └── init
├── scripts/
│   ├── check_tool_versions.py
│   └── generate_sbom.py
├── Deliverables/
├── Documentation/
│   └── sbom/
│       ├── api.cdx.json
│       └── web.cdx.json
├── compose.yaml
├── compose.infra.yaml
├── package.json
├── package-lock.json
├── .env.example
├── .env
├── .gitignore
├── .pre-commit-config.yaml
└── README.md
```

### Important files

- `package.json` — root scripts used to install, run, stop and test the whole repository.
- `compose.yaml` — defines the services, networks, volumes, environment variables, and service dependencies.
- `compose.infra.yaml` — override used by `npm run dev` to publish PostgreSQL and MinIO on `127.0.0.1`.
- `apps/web/Dockerfile` — builds the React frontend and packages it with Nginx.
- `apps/api/Dockerfile` — builds the Python API image.
- `infra/nginx/default.conf` — configures frontend serving and API routing.
- `apps/api/src/main.py` — FastAPI application entry point.
- `apps/api/pyproject.toml` — Python project metadata and dependencies.
- `apps/api/uv.lock` — locked Python dependency versions.
- `scripts/generate_sbom.py` — generates the CycloneDX SBOMs from the dependency lockfiles.
- `Documentation/sbom/api.cdx.json` — SBOM for the API application dependencies.
- `Documentation/sbom/web.cdx.json` — SBOM for the frontend application dependencies.
- `.env.example` — template containing the configuration variables required for local development.
- `.env` — local configuration containing developer-specific credentials. This file must not be committed to Git.

## Prerequisites

Before starting, install the following:

1. Git
2. Docker Desktop on Windows or macOS, or Docker Engine with the Docker Compose plugin on Linux
3. Node.js and npm (the versions pinned in `apps/web/Dockerfile` and `apps/web/package.json`), needed for the root scripts
4. [uv](https://docs.astral.sh/uv/getting-started/installation/) (the version pinned in `apps/api/pyproject.toml`), needed for the local mode and the API tests
5. A Docker Hub account (recommended)

You do **not** need to install Python, PostgreSQL, or MinIO separately: uv provides the Python runtime and Docker provides the database and object storage.

### 1. Install Git

Download Git from [git-scm.com](https://git-scm.com/downloads) if it is not already installed.

Verify the installation:

```bash
git --version
```

### 2. Install Docker

#### Windows

1. Check the [Docker Desktop system requirements](https://docs.docker.com/desktop/setup/install/windows-install/).
2. Install or update WSL 2 if required by your system.
3. Download Docker Desktop from the [official Docker website](https://www.docker.com/products/docker-desktop/).
4. Follow the installation instructions.
5. Start Docker Desktop and wait until the Docker Engine is running.

Docker Desktop for Windows commonly uses the WSL 2 backend.

#### macOS

1. Visit the [Docker Desktop installation guide](https://docs.docker.com/desktop/setup/install/mac-install/).
2. Download the version appropriate for your Mac's processor.
3. Install and launch Docker Desktop.
4. Wait until the Docker Engine is running.

#### Linux

Install Docker Engine and the Compose plugin using the official instructions for your distribution:

- [Install Docker Engine](https://docs.docker.com/engine/install/)
- [Install the Docker Compose plugin](https://docs.docker.com/compose/install/linux/)

### 3. Verify Docker

Open a terminal and run:

```bash
docker --version
docker compose version
docker info
```

The first two commands should print the installed versions. `docker info` should display information about both the client and the running server.

If `docker info` reports that it cannot connect to the Docker daemon, start Docker Desktop or the Docker Engine before continuing.

### 4. Install Node.js and uv

Install [Node.js](https://nodejs.org/) (npm is included) and [uv](https://docs.astral.sh/uv/getting-started/installation/), then verify:

```bash
node --version
npm --version
uv --version
```

### 5. Create a Docker Hub account

Docker Hub hosts many of the public container images used by this project.

1. Visit [Docker Hub](https://hub.docker.com/).
2. Create an account or sign in.
3. Verify your email address if requested.

A Docker Hub account is generally not required to pull public images, but signing in can help with image-pull limits.

### 6. Log in to Docker Hub from the command line

Run:

```bash
docker login
```

Follow the prompts to authenticate. Depending on your Docker CLI version and configuration, Docker may open a browser for authentication or ask for credentials.

If you use a personal access token, generate one through your Docker Hub account's security settings and use it instead of your account password when prompted for a password.

For unattended environments, use an appropriately scoped access token rather than storing your account password in scripts.

Verify the login by pulling a public image:

```bash
docker pull hello-world
```

Docker should download the image if it is not already available locally.

## Getting Started

### 1. Clone the repository

Open PowerShell, Terminal, or another command-line shell and navigate to the directory where you want the project.

```bash
git clone https://github.com/amosproj/amos2026ws02-engineering-knowledge-advisor.git
cd amos2026ws02-engineering-knowledge-advisor
```

If you already cloned the repository, navigate to the existing repository directory instead.

### 2. Create your local environment file

The project uses a `.env` file for local configuration.

Copy the example file:

**Windows PowerShell**

```powershell
Copy-Item .env.example .env
```

**macOS/Linux**

```bash
cp .env.example .env
```

Open `.env` in your editor. It contains the PostgreSQL and MinIO configuration.

For example:

```dotenv
POSTGRES_DB=engineering_knowledge
POSTGRES_USER=eka_app
POSTGRES_PASSWORD=replace_with_a_unique_long_password

MINIO_ROOT_USER=eka_minio_admin
MINIO_ROOT_PASSWORD=replace_with_another_unique_long_password

S3_BUCKET=engineering-documents
S3_REGION=us-east-1
```

The same file holds the frontend configuration. [`VITE_*` variables](https://vite.dev/guide/env-and-mode):

- are **PUBLIC**: they are embedded in the browser bundle and readable by anyone
- **MUST NOT** hold secrets (e.g. passwords, API keys)
- **MUST** be added to `.env`, the `web` build `args` in `compose.yaml`, `apps/web/Dockerfile`, `apps/web/src/vite-env.d.ts` and `apps/web/src/utils/env.ts`
- are read at build time: rebuild the frontend after changing one

Frontend variables that are not exposed to the browser use the `WEB_` prefix (e.g. `WEB_API_PROXY_TARGET`, used only by the Vite dev server).

Use different, unique passwords for your local environment. Do not commit `.env` to Git or share real credentials in issues, screenshots, or messages.

Keep `.env.example` updated whenever required environment variables change, but use placeholder values in that file.

### 3. Install the dependencies

From the repository root, run:

```bash
npm install        # installs the root task runner (concurrently)
npm run setup      # installs the web (npm ci) and API (uv sync) dependencies
```

### 4. Install the pre-commit hook

This installs the pre-commit Git hook (ruff, pyright, pytest, SBOM and tool-version checks) in the venv created by `npm run setup`:

```bash
uv run --directory apps/api pre-commit install
```

Optional manual test-run of all hooks:

```bash
uv run --directory apps/api pre-commit
```

To uninstall the hook:

```bash
uv run --directory apps/api pre-commit uninstall
```

### 5. Validate the Docker Compose configuration (optional)

```bash
docker compose config --quiet
```

If the command finishes without errors, Docker Compose can parse the configuration and resolve its environment variables.

If it reports missing variables or configuration errors, check that you created `.env` in the repository root and that its variable names match those used in `compose.yaml`.

## Running the Application

There are two ways to run the application. Both are started from the repository root with a single command.

| Mode                | Command              | Use it when                                                      |
| ------------------- | -------------------- | ---------------------------------------------------------------- |
| **Local dev**       | `npm run dev`        | You are changing code: the API and the web app reload on change. |
| **Docker (Compose)** | `npm run docker:up` | You want the production-like stack, exactly as it is deployed.   |

### Local dev: `npm run dev`

```bash
npm run dev
```

This command:

1. Starts PostgreSQL and MinIO in Docker, published on `127.0.0.1` through `compose.infra.yaml` (it waits until PostgreSQL is healthy).
2. Runs the API with auto-reload on `http://127.0.0.1:8000`.
3. Runs the Vite dev server with hot module replacement on `http://localhost:5173`.

The two apps run in parallel in the same terminal, with their logs prefixed by `api` and `web`. Vite forwards `/api` requests to the API, so the web app always calls a same-origin `/api`.

If port 5432 is already used by a local PostgreSQL, set `POSTGRES_PORT` (for example `5433`) in `.env` to change the host port published for the database.

### Docker (Compose):

```bash
npm run docker:up
```

This builds the images and starts the whole stack (PostgreSQL, MinIO, API, Nginx + frontend) in the background. The application is available at `http://localhost:8080`.

The first startup may take several minutes, depending on your internet connection and whether the required images have already been downloaded.

This mode does not hot-reload: run `npm run docker:up` again to rebuild after changing code or dependencies.

### Run only a part of the stack

The sub-commands used by `npm run dev` are also available on their own:

```bash
npm run dev:infra   # only PostgreSQL and MinIO (Docker)
npm run dev:api     # only the API, with auto-reload (needs dev:infra for the database)
npm run dev:web     # only the Vite dev server
```

## Stopping the Application

| Started with         | Stop with                                                         |
| -------------------- | ----------------------------------------------------------------- |
| `npm run dev`        | **Ctrl+C** (stops the API and the web app), then `npm run dev:stop` |
| `npm run docker:up`  | `npm run docker:down`                                             |

`npm run dev:stop` stops the PostgreSQL and MinIO containers started by `npm run dev`. After **Ctrl+C** they keep running in the background, which makes the next `npm run dev` start faster.

`npm run docker:down` stops and removes the containers and the Compose network. Named volumes are preserved, so your local database and object-storage data remain available when you start the application again.

To delete the data, see [Docker Operations](#docker-operations).

## Testing the Services

These checks work in both modes. Use `http://localhost:5173` for the local dev mode and `http://localhost:8080` for the Docker mode.

### Frontend

Open [http://localhost:5173](http://localhost:5173) (local dev) or [http://localhost:8080](http://localhost:8080) (Docker). The React frontend should load.

### API health check

Open [http://localhost:5173/api/health/live](http://localhost:5173/api/health/live) (local dev, through the Vite proxy) or [http://localhost:8080/api/health/live](http://localhost:8080/api/health/live) (Docker, through Nginx). Or from a terminal:

```bash
curl http://localhost:5173/api/health/live
curl http://localhost:8080/api/health/live
```

Expected response:

```json
{ "status": "ok" }
```

This confirms that the proxy (Vite or Nginx) can forward the health-check request to FastAPI.

### PostgreSQL

Check whether PostgreSQL is accepting connections:

```bash
docker compose exec db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

The output should indicate that the server is accepting connections.

Check whether the pgvector extension is available:

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT name FROM pg_available_extensions WHERE name = '\''vector'\'';"'
```

This checks availability of the extension; it does not enable it in the database.

### PostgreSQL initialization and testing (Windows PowerShell)

You can manually execute the PostgreSQL initialization script from Windows PowerShell using:

```powershell
Get-Content .\infra\postgres\init | docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

This sends the SQL initialization script to the PostgreSQL container.

To verify that the database is working and the test table exists, run:

```powershell
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT * FROM init_test;"'
```

If initialization and testing are successful, the query should return the test records stored in `init_test`.

**Note:** Run these commands from the repository root while the database container is running. PostgreSQL's automatic initialization scripts run only when the database data directory is first created. Manual execution allows you to test the SQL script against an existing database.

### MinIO

Check the MinIO service logs:

```bash
docker compose logs --tail 50 minio
```

The API container can also check MinIO's internal health endpoint:

```bash
docker compose exec api uv run --no-sync python -c "import urllib.request; print(urllib.request.urlopen('http://minio:9000/minio/health/live', timeout=5).status)"
```

A healthy MinIO service should return HTTP status `200`.

## Running the Tests

From the repository root:

```bash
npm test            # API tests, then web tests
npm run test:api    # API only (pytest)
npm run test:web    # web only (Vitest)
```

CI (`.github/workflows/api-tests.yaml` and `.github/workflows/web-tests.yaml`) runs the checks on every pull request.

## Working on a Single App

The root scripts cover running and testing. The commands below exist only inside one app and have no root equivalent.

### Web (`apps/web`)

Frontend tests use [Vitest](https://vitest.dev) and `*.test.ts` files. CI also runs ESLint, Prettier and TypeScript:

```bash
npm --prefix apps/web run test:watch   # re-run the tests on change
npm --prefix apps/web run lint         # ESLint
npm --prefix apps/web run format       # Prettier (writes the files)
npm --prefix apps/web run build        # type-check (tsc) and production build
```

### API (`apps/api`)

The API linter and type checker run through the pre-commit hook (see [Getting Started](#4-install-the-pre-commit-hook)). To run them by hand:

```bash
uv run --project apps/api ruff check apps/api
uv run --project apps/api pyright --project apps/api
```

## Docker Operations

These commands inspect or tune the Docker mode and have no root script.

### Follow the logs

```bash
docker compose logs -f            # all services
docker compose logs -f api        # one service: api, db, minio or web
```

### Check the current service status

```bash
docker compose ps
```

### Rebuild a single service

```bash
docker compose up --build -d api
docker compose up --build -d web
```

Compose also starts the required dependencies when necessary.

### Stop and restart without removing the containers

```bash
docker compose stop
docker compose start
```

### View the merged Compose configuration

```bash
docker compose config
```

Review the output carefully before sharing it because resolved configuration can contain environment values.

### Reset the local data

**Warning:** The following command removes the Compose-managed volumes and permanently deletes the corresponding local database and object-storage data:

```bash
docker compose down -v
```

Use it only when you deliberately want to reset your local environment.

## Software Bill of Materials

CycloneDX SBOMs for the API and frontend are generated from the lockfiles, enforced by a pre-commit hook and checked in CI. Setup, regeneration, and tool version requirements are described in [Documentation/sbom/README.md](Documentation/sbom/README.md).

## Troubleshooting

### Docker cannot connect to the daemon

Start Docker Desktop and wait for the engine to finish starting. Then retry:

```bash
docker info
```

### Image pull fails

Check your internet connection and Docker Hub login:

```bash
docker login
docker compose pull
```

If a public image is unavailable or access is denied, inspect the image name and tag in `compose.yaml`. A login cannot fix an invalid or removed image reference.

### A service exits or restarts repeatedly

Check its logs:

```bash
docker compose ps
docker compose logs --tail 100
```

### The frontend is unavailable

In the Docker mode, verify that the web container is running and inspect its logs:

```bash
docker compose ps
docker compose logs web
```

Then check `http://localhost:8080`. In the local dev mode, check the `web` lines of the `npm run dev` terminal and `http://localhost:5173`.

### The API health check fails

In the local dev mode, check the `api` lines of the `npm run dev` terminal. In the Docker mode, inspect the API and Nginx logs:

```bash
docker compose logs api
docker compose logs web
```

Confirm that the API is running and that the proxy forwards `/api/` requests to it on port `8000`.

### A port is already in use

- Port `5432` (local dev, PostgreSQL): set `POSTGRES_PORT=5433` (or any free port) in `.env`.
- Port `8080` (Docker mode, web): change the published port in `compose.yaml`. For example:

```yaml
ports:
  - "127.0.0.1:8081:80"
```

The frontend will then be available at `http://localhost:8081`.

## Security Notes

- Never commit `.env`, credentials, access tokens, or other secrets.
- Use unique local development credentials.
- Do not expose PostgreSQL or MinIO administrative interfaces publicly. `compose.infra.yaml` publishes them on `127.0.0.1` only.
- Keep Docker Desktop, Docker Engine, and container images updated.
- Use stronger secret-management practices for shared environments and production deployments.
- Treat local container configuration as a development setup until production security, storage initialization, backups, and deployment requirements have been reviewed.

## Project Status

The initial containerized architecture is in place, including the React frontend, FastAPI health endpoint, PostgreSQL with pgvector support, MinIO, and Nginx routing.

The next development stages include implementing application features, defining database schemas and migrations, initializing object storage, and building the document-processing and knowledge-retrieval workflows.

## Command Reference

Commands sorted by priority for someone who wants to run the application. Run them from the repository root.

| #   | Command                                                    | What it does                                                                         |
| --- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 1   | `npm install`                                              | Installs the root task runner (once).                                                |
| 2   | `npm run setup`                                            | Installs the web and API dependencies (once, and after dependency changes).          |
| 3   | `npm run dev`                                              | Starts PostgreSQL and MinIO in Docker, then the API and the web app with auto-reload. |
| 4   | `npm run docker:up`                                        | Builds and starts the whole stack in Docker on `http://localhost:8080`.              |
| 5   | `npm run dev:stop`                                         | Stops the PostgreSQL and MinIO containers started by `npm run dev`.                  |
| 6   | `npm run docker:down`                                      | Stops and removes the Docker stack (data volumes are kept).                          |
| 7   | `npm test`                                                 | Runs the API tests, then the web tests.                                              |
| 8   | `npm run test:api` / `npm run test:web`                    | Runs the API tests or the web tests only.                                            |
| 9   | `npm run dev:infra`                                        | Starts only PostgreSQL and MinIO.                                                    |
| 10  | `npm run dev:api` / `npm run dev:web`                      | Starts only the API or only the Vite dev server.                                     |
| 11  | `docker compose logs -f [service]`                         | Follows the logs of the Docker stack (or of one service).                            |
| 12  | `docker compose ps`                                        | Shows the state of the Docker services.                                              |
| 13  | `docker compose up --build -d <service>`                   | Rebuilds and restarts one Docker service.                                            |
| 14  | `npm --prefix apps/web run test:watch` / `lint` / `format` | Web only: tests in watch mode, ESLint, Prettier.                                     |
| 15  | `uv run --project apps/api ruff check apps/api`            | API only: lints the Python code.                                                     |
| 16  | `uv run --directory apps/api pre-commit install`           | Installs the pre-commit Git hook (once).                                             |
| 17  | `docker compose down -v`                                   | **Deletes** the local database and object-storage data.                              |
