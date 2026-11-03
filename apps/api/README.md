# Engineering Knowledge Advisor API

FastAPI backend. Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

## Configuration

| Variable                  | Values                                   | Default              |
|---------------------------|------------------------------------------|----------------------|
| `API_PROFILE`             | `dev`, `prod`                            | `dev`                |
| `API_DATABASE_URL`        | `postgresql+psycopg://user:pw@host/db`   | none (required)      |
| `API_OGRAG_ONTOLOGY_PATH` | JSON-LD ontology file                    | none (required)      |
| `API_S3_ENDPOINT_URL`     | S3 endpoint, e.g. `http://minio:9000`    | none (required)      |
| `API_S3_BUCKET`           | bucket of the uploaded files             | none (required)      |
| `API_S3_ACCESS_KEY`       | S3 access key                            | none (required)      |
| `API_S3_SECRET_KEY`       | S3 secret key                            | none (required)      |
| `API_S3_REGION`           | S3 region, e.g. `us-east-1`              | none (required)      |
| `API_S3_PUBLIC_URL`       | where the browser reaches the storage, e.g. `/storage` | none (required) |

Settings are read in this order:
1. environment variables (prefix `API_`)
2. `.env`
3. defaults

`.env` is used from the directory the backend is started from:
- start from `apps/api/` => `apps/api/.env`
- start from repository root with `--directory` => `apps/api/.env`
- start from repository root with `--project` => `.env` at root

## Database

Postgres. Schema changes are Alembic migrations in `migrations/`:
```sh
uv run --directory apps/api alembic upgrade head                                # apply
uv run --directory apps/api alembic revision --autogenerate -m "what changed"   # review the file
uv run --directory apps/api alembic check                                       # models and migrations agree
```

Text columns: `String` (`varchar` without a length) for ids and short values, `Text` for free form text. Postgres stores both the same way. To set a limit, use ``varchar(n)``.

## Knowledge records (OG-RAG)

Loaded on start with the ontology. Invalid ontology stops the start.

| Route                                               | What                                                      |
|-----------------------------------------------------|-----------------------------------------------------------|
| `PUT /api/v1/records/{id}`                          | Create or replace a record, links must be valid. Not for machines, assembly groups and CAD files |
| `GET /api/v1/records`                               | All records by id                                         |
| `GET /api/v1/records/review`                        | Records that lost their last link and await a review      |
| `DELETE /api/v1/records/{id}[?delete_orphans=true]` | Delete and unlink everywhere, records left without a link are marked for review (or deleted). Not for machines, assembly groups and CAD files |

## Machines, assembly groups and CAD files

Stored as records (CadFile `partOf` AssemblyGroup `partOf` Machine), upload state in `cad_uploads`. Routes in the OpenAPI docs. Upload: register the files, `POST` each one with its form, then call `/complete`.

## Run

```sh
uv run uvicorn main:app
```

Or from repository root using root `.env`:
```sh
uv run --project apps/api uvicorn main:app
```

Or from repository root using API's `.env`:
```sh
uv run --directory apps/api uvicorn main:app
```

On Windows, async psycopg needs a selector event loop. Add this flag to any of the above:
```sh
uv run uvicorn main:app --loop asyncio:SelectorEventLoop
```

## Storage and background jobs

Uploaded files are stored in S3 (MinIO in Docker). The `migrate` service applies the migrations, then creates the bucket if it does not exist yet (`python -m storage.s3`).

The `worker` service (`python -m worker`, code in `src/worker/`) checks the uploaded STEP files and, every hour, deletes abandoned uploads and orphan objects. It touches `/tmp/worker-heartbeat` every 10 s, and the container is reported unhealthy when the file is older than one minute.

## Test & Lint

```sh
uv run pre-commit                       # lint + type check + tests
uv run pytest                           # tests only
```

Or from repository root:
```sh
uv run --directory apps/api pre-commit  # lint + type check + tests
uv run --directory apps/api pytest      # tests only
```

Postgres tests `tests/test_pg.py` run only when `API_TEST_DATABASE_URL` is set. Test database is wiped on test run.

## Sample data for API tests:

### Machine
```json
{
  "@type": "Machine",
  "identifier": "RC-01",
  "name": "Robot cell",
  "description": "Robot cell for loading anodised aluminium housings",
  "customer": "Example GmbH"
}
```

### AsssemblyGroup
```json
 {
  "@type": "AssemblyGroup",
  "identifier": "AG-IT-003",
  "name": "Input tray",
  "partOf": "RC-01",
  "hasCharacteristic": {
    "function": "Feed parts to the robot",
    "loadingMode": "drawer",
    "payloadKg": 12,
    "partSizeMinMm": 20,
    "partSizeMaxMm": 80
  },
  "hasCategory": {
    "functionArea": "Feeding and dosing",
    "reuseStatus": "reuse candidate",
    "tag": ["tray", "drawer"]
  },
  "hasComponent": [
    {"name": "Guide rail", "partId": "4711-0815", "quantity": 2},
    {"name": "Drawer slide", "partId": "4711-0900", "quantity": 1}
  ]
}
```

### CadFile
```json
{
  "@type": "CadFile",
  "name": "RC-01_input_tray.step",
  "format": "STEP",
  "partOf": "AG-IT-003"
}
```

### KnowledgeItem
```json
{
  "@type": "KnowledgeItem",
  "itemType": "lesson learned",
  "scope": "machine-specific",
  "name": "Nest chamfer for anodised parts",
  "statement": "Chamfer the nest edges, anodised parts jam on sharp edges.",
  "reasoning": "The anodised layer scratches and the part tilts in the nest.",
  "recommendation": "0.5 mm chamfer on all nest edges.",
  "confidence": "established practice",
  "appliesTo": ["AG-IT-003"]
}
```
