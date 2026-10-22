# Engineering Knowledge Advisor

An application for organizing and accessing engineering knowledge, with the goal of helping users find relevant information across engineering documents and other knowledge sources.

The project uses a containerized web application architecture with a React frontend, a FastAPI backend, PostgreSQL with pgvector, and S3-compatible object storage through MinIO.

## Table of Contents

- [Project Overview](#project-overview)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Starting the Application](#starting-the-application)
- [Testing the Services](#testing-the-services)
- [Stopping the Application](#stopping-the-application)
- [Development Workflow](#development-workflow)
- [Software Bill of Materials](#software-bill-of-materials)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)

## Project Overview

The Engineering Knowledge Advisor is being developed as a web application for working with engineering knowledge.

The architecture separates the frontend, API, database, and object storage into individual services. Docker Compose manages these services so that developers can run a consistent local environment without manually installing each application's runtime dependencies.

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

## Repository Structure

```text
engineering-knowledge-advisor/
├── apps/
│   ├── api/
│   │   ├── src/
│   │   │   └── api/
│   │   │       ├── __init__.py
│   │   │       └── main.py
│   │   ├── Dockerfile
│   │   ├── .dockerignore
│   │   ├── pyproject.toml
│   │   ├── uv.lock
│   │   └── README.md
│   └── web/
│       ├── src/
│       ├── public/
│       ├── Dockerfile
│       ├── .dockerignore
│       ├── package.json
│       └── package-lock.json
├── infra/
│   └── nginx/
│       └── default.conf
├── scripts/
│   └── generate_sbom.py
├── Deliverables/
├── Documentation/
│   └── sbom/
│       ├── api.cdx.json
│       └── web.cdx.json
├── compose.yaml
├── .env.example
├── .env
├── .gitignore
├── .pre-commit-config.yaml
└── README.md
```

### Important files

- `compose.yaml` — defines the services, networks, volumes, environment variables, and service dependencies.
- `apps/web/Dockerfile` — builds the React frontend and packages it with Nginx.
- `apps/api/Dockerfile` — builds the Python API image.
- `infra/nginx/default.conf` — configures frontend serving and API routing.
- `apps/api/src/api/main.py` — FastAPI application entry point.
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
3. A Docker Hub account (recommended)

You do **not** need to install Python, Node.js, PostgreSQL, or MinIO separately to run the containerized application. Docker handles the required application runtimes and service images.

### 1. Install Git

Download Git from [git-scm.com](https://git-scm.com/downloads) if it is not already installed.

Verify the installation:

```powershell
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

```powershell
docker --version
docker compose version
docker info
```

The first two commands should print the installed versions. `docker info` should display information about both the client and the running server.

If `docker info` reports that it cannot connect to the Docker daemon, start Docker Desktop or the Docker Engine before continuing.

### 4. Create a Docker Hub account

Docker Hub hosts many of the public container images used by this project.

1. Visit [Docker Hub](https://hub.docker.com/).
2. Create an account or sign in.
3. Verify your email address if requested.

A Docker Hub account is generally not required to pull public images, but signing in can help with image-pull limits.

### 5. Log in to Docker Hub from the command line

Run:

```powershell
docker login
```

Follow the prompts to authenticate. Depending on your Docker CLI version and configuration, Docker may open a browser for authentication or ask for credentials.

If you use a personal access token, generate one through your Docker Hub account's security settings and use it instead of your account password when prompted for a password.

For unattended environments, use an appropriately scoped access token rather than storing your account password in scripts.

Verify the login by pulling a public image:

```powershell
docker pull hello-world
```

Docker should download the image if it is not already available locally.

## Getting Started

### 1. Clone the repository

Open PowerShell, Terminal, or another command-line shell and navigate to the directory where you want the project.

```powershell
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

Use different, unique passwords for your local environment. Do not commit `.env` to Git or share real credentials in issues, screenshots, or messages.

Keep `.env.example` updated whenever required environment variables change, but use placeholder values in that file.

### 3. Validate the Docker Compose configuration

From the repository root, run:

```powershell
docker compose config --quiet
```

If the command finishes without errors, Docker Compose can parse the configuration and resolve its environment variables.

If it reports missing variables or configuration errors, check that you created `.env` in the repository root and that its variable names match those used in `compose.yaml`.

## Starting the Application

Start all services with one command:

```powershell
docker compose up --build
```

Docker Compose will:

1. Pull the required base images if they are not available locally.
2. Build the frontend and backend images.
3. Create the required Docker network and persistent volumes.
4. Start PostgreSQL, MinIO, the API, and the web server in dependency order.
5. Display service logs in the terminal.

The first startup may take several minutes, depending on your internet connection and whether the required images have already been downloaded.

When startup completes, keep this terminal open to see the logs.

### Run in the background

If you prefer to use the terminal for other tasks, start the application in detached mode:

```powershell
docker compose up --build -d
```

Follow the logs with:

```powershell
docker compose logs -f
```

To view the status of the services:

```powershell
docker compose ps
```

## Testing the Services

### Frontend

Open:

[http://localhost:8080](http://localhost:8080)

The React frontend should load through Nginx.

### API health check

Open:

[http://localhost:8080/api/health/live](http://localhost:8080/api/health/live)

Expected response:

```json
{ "status": "ok" }
```

This confirms that Nginx can forward the health-check request to FastAPI.

### PostgreSQL

Check whether PostgreSQL is accepting connections:

```powershell
docker compose exec db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

The output should indicate that the server is accepting connections.

Check whether the pgvector extension is available:

```powershell
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT name FROM pg_available_extensions WHERE name = ''vector'';"'
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

```powershell
docker compose logs --tail 50 minio
```

The API container can also check MinIO's internal health endpoint:

```powershell
docker compose exec api uv run --no-sync python -c "import urllib.request; print(urllib.request.urlopen('http://minio:9000/minio/health/live', timeout=5).status)"
```

A healthy MinIO service should return HTTP status `200`.

### View logs for a specific service

```powershell
docker compose logs api
docker compose logs db
docker compose logs minio
docker compose logs web
```

To follow one service's logs continuously, add `-f`, for example:

```powershell
docker compose logs -f api
```

## Stopping the Application

If you started the application in the foreground, press **Ctrl+C** in the terminal running Compose.

Then run:

```powershell
docker compose down
```

This stops and removes the containers and the Compose network. Named volumes are preserved, so your local database and object-storage data remain available when you start the application again.

To stop the services while retaining the containers:

```powershell
docker compose stop
```

To restart stopped services:

```powershell
docker compose start
```

**Warning:** The following command removes the Compose-managed volumes and permanently deletes the corresponding local database and object-storage data:

```powershell
docker compose down -v
```

Use it only when you deliberately want to reset your local environment.

## Development Workflow

### Rebuild after changing dependencies or Docker configuration

```powershell
docker compose up --build
```

### Restart after changing application code

For changes that are copied into the Docker image, rebuild the relevant service:

```powershell
docker compose up --build api
```

For frontend changes:

```powershell
docker compose up --build web
```

Compose will also start required dependencies when necessary.

### Check the current service status

```powershell
docker compose ps
```

### View the merged Compose configuration

```powershell
docker compose config
```

Review the output carefully before sharing it because resolved configuration can contain environment values.

### Work locally without Docker

The frontend can also be run independently using Node.js and npm:

```powershell
cd apps/web
npm ci
npm run dev
```

The API can be run locally with uv installed:

```powershell
uv sync --directory apps/api
uv run --directory apps/api uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

The local API runs at `http://127.0.0.1:8000`. Local execution requires any external services that the code actually uses to be configured and reachable.

## Software Bill of Materials

The API and frontend SBOMs are generated automatically from their dependency lockfiles. A pre-commit hook regenerates the inventories when dependency-related files change, and a required CI check independently verifies that the committed SBOMs are current.

These are application-package inventories. They do not inventory all operating-system packages in the Docker images or the complete Nginx image.

### Install the pre-commit hook

Run this once after cloning the repository:

```bash
uv tool install pre-commit
pre-commit install
```

The hook requires Python, uv, and npm on your `PATH`.

### How the hook behaves

The hook only runs when `apps/api/pyproject.toml`, `apps/api/uv.lock`, `apps/web/package.json`, `apps/web/package-lock.json`, the generator script, or the SBOM files themselves are staged.

When the hook updates an SBOM, the commit stops so you can review the changes:

```bash
git diff -- Documentation/sbom/
git add Documentation/sbom/
git commit -m "Update dependencies and SBOMs"
```

### Regenerate the SBOMs manually

```bash
python scripts/generate_sbom.py
```

Verify that the committed files are current (this is what CI runs):

```bash
python scripts/generate_sbom.py --check
```

Use the same uv and npm versions locally and in CI. npm records its generator version in the SBOM, so a different npm version produces a different file.

## Troubleshooting

### Docker cannot connect to the daemon

Start Docker Desktop and wait for the engine to finish starting. Then retry:

```powershell
docker info
```

### Image pull fails

Check your internet connection and Docker Hub login:

```powershell
docker login
docker compose pull
```

If a public image is unavailable or access is denied, inspect the image name and tag in `compose.yaml`. A login cannot fix an invalid or removed image reference.

### A service exits or restarts repeatedly

Check its logs:

```powershell
docker compose ps
docker compose logs --tail 100
```

### The frontend is unavailable

Verify that the web container is running and inspect its logs:

```powershell
docker compose ps
docker compose logs web
```

Then check `http://localhost:8080`.

### The API health check fails

Inspect the API and Nginx logs:

```powershell
docker compose logs api
docker compose logs web
```

Confirm that the API is running and that Nginx forwards `/api/` requests to the `api` service on port `8000`.

### A port is already in use

If host port `8080` is occupied, change the published port in `compose.yaml`. For example:

```yaml
ports:
  - "127.0.0.1:8081:80"
```

The frontend will then be available at `http://localhost:8081`.

## Security Notes

- Never commit `.env`, credentials, access tokens, or other secrets.
- Use unique local development credentials.
- Do not expose PostgreSQL or MinIO administrative interfaces publicly.
- Keep Docker Desktop, Docker Engine, and container images updated.
- Use stronger secret-management practices for shared environments and production deployments.
- Treat local container configuration as a development setup until production security, storage initialization, backups, and deployment requirements have been reviewed.

## Project Status

The initial containerized architecture is in place, including the React frontend, FastAPI health endpoint, PostgreSQL with pgvector support, MinIO, and Nginx routing.

The next development stages include implementing application features, defining database schemas and migrations, initializing object storage, and building the document-processing and knowledge-retrieval workflows.
