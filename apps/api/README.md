# Engineering Knowledge Advisor API

FastAPI backend. Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

## Configuration

| Variable                  | Values                                   | Default              |
|---------------------------|------------------------------------------|----------------------|
| `API_PROFILE`             | `dev`, `prod`                            | `dev`                |
| `API_DATABASE_URL`        | `postgresql+psycopg://user:pw@host/db`   | none (required)      |
| `API_OGRAG_ONTOLOGY_PATH` | JSON-LD ontology file                    | none (required)      |
| `API_OGRAG_EMBED_DIM`     | embedding dimensionality, given by embedding model | `384`      |

Settings are read in this order:
1. environment variables (prefix `API_`)
2. `.env`
3. defaults

`.env` is used from the directory the backend is started from:
- start from `apps/api/` => `apps/api/.env`
- start from repository root with `--directory` => `apps/api/.env`
- start from repository root with `--project` => `.env` at root

## Database

Postgres with [pgvector](https://github.com/pgvector/pgvector). Schema changes are Alembic migrations in `migrations/`:
```sh
uv run --directory apps/api alembic upgrade head                                # apply
uv run --directory apps/api alembic revision --autogenerate -m "what changed"   # review the file
uv run --directory apps/api alembic check                                       # models and migrations agree
```

## Knowledge records (OG-RAG)

Loaded on start with the ontology. Invalid ontology stops the start.

| Route                                               | What                                                      |
|-----------------------------------------------------|-----------------------------------------------------------|
| `PUT /api/v1/records/{id}`                          | Create or replace a record, links must be valid           |
| `GET /api/v1/records`                               | All records by id                                         |
| `GET /api/v1/records/review`                        | Records that lost their last link and await a review      |
| `DELETE /api/v1/records/{id}[?delete_orphans=true]` | Delete and unlink everywhere, records left without a link are marked for review (or deleted) |

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
  "hasCadFile": {
    "name": "RC-01_input_tray.CATProduct",
    "format": "CATIA V5"
  },
  "hasComponent": [
    {"name": "Guide rail", "partId": "4711-0815", "quantity": 2},
    {"name": "Drawer slide", "partId": "4711-0900", "quantity": 1}
  ]
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
