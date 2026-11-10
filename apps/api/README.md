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

Text columns: `String` (`varchar` without a length) for ids and short values, `Text` for free form text. Postgres stores both the same way. To set a limit, use ``varchar(n)``. Table, column, index and constraint names live in `src/db/names.py`, tables in `src/db/tables.py`.

To rename a table or column:
1. Change the enum value in `db/names.py`.
2. Add a new revision that renames (`op.alter_column(table, old, new_column_name=new)`, `op.rename_table(old, new)`). Autogenerate writes DROP + ADD, which loses the data.
3. Run `alembic check`.

## Knowledge Records

Loaded on start with the ontology. Invalid ontology stops the start. JSON fields, query and path parameters are camelCase.

| Route                                               | What                                                                       |
|-----------------------------------------------------|----------------------------------------------------------------------------|
| `POST /api/v1/records`                              | Create a record with a generated id                                        |
| `PUT /api/v1/records/{id}`                          | Upsert a record with client's id, links must be valid                      |
| `PATCH /api/v1/records/{id}`                        | Change only sent properties (JSON Merge Patch / RFC 7396)                  |
| `GET /api/v1/records[?cls=&parentId=&include=]`     | All records by id, or those of a class / with a parent link to `parentId`  |
| `GET /api/v1/records/{id}[?include=]`               | One record                                                                 |
| `GET /api/v1/records/{id}/tree[?depth=]`            | The record with every record below it                                      |
| `GET /api/v1/records/{id}/ancestors[?depth=]`       | The record with its parents up to the top                                  |
| `GET /api/v1/records/review`                        | Records that lost their last parent link and await review                  |
| `DELETE /api/v1/records/{id}[?deleteOrphans=true]`  | Delete record, orphan records left without a parent link are marked for review or deleted |
| `POST /api/v1/records/{id}/upload-form`             | Upload form for the file of an `og:file` record                            |
| `POST /api/v1/records/{id}/complete`                | Confirm the upload, queue the file for processing                          |
| `GET /api/v1/ontology`                              | Every class with its properties and annotations                            |

`include=status,children,upload` wraps each record as `{"record": ..., "status": ..., "children": [...], "upload": ...}`:
- `status`: current most urgent upload status of its files and parents the file records point to
- `children`: records whose parent link points to it, file records included
- `upload`: upload metadata on file records

### Parallel editing (If-Match)

TODO: can become a problem if multiple people want to edit different parts of the same record at the same time

Postgres `xmin`: `ETag` header of `GET /records/{id}`, and a `version` field in write responses, include wrappers, `/tree`, `/ancestors` and `/records/review`.

Send it back as `If-Match: "<version>"` with `PUT`, `PATCH` or `DELETE`. If someone saved the record in between, the answer is `412` and nothing changes. In that case the record should be read again.

`If-Match: *` accepts any existing record. Without `If-Match` the write is not checked (imports, scripts).

## Files

A record of a class marked `og:file` (CadFile) carries one file, upload state in `cad_uploads`, the file in S3 under
`files/{id}/`. A machine has one CAD file (`og:maxPerParent`), a second one answers `409` with `max_per_parent`. The file bytes never pass the API:

1. `POST /records` creates the record without file (status `empty`).
2. `POST /records/{id}/upload-form` with `{"size": ...}` returns a presigned form.
3. Client posts the file straight to S3 based on form, then `POST /records/{id}/complete`.
4. Worker checks the file: `processing`, then `ready` or `failed`.

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

Uploaded files are stored in S3 (MinIO in Docker). The `migrate` service applies the migrations, then creates the bucket if it does not exist yet (`python -m services.s3`).

The `cad-file-worker` service (`python -m cad_file_worker`, code in `src/cad_file_worker/`) checks the uploaded STEP files and, every hour, deletes abandoned uploads and orphan objects, but their records stay. It touches `/tmp/cad-file-worker-heartbeat` every 10 s, and the container is reported unhealthy when the file is older than one minute.

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

`POST /records` is for generated IDs and takes the same bodies.

### Machine
`PUT /records/RC-01`
```json
{
  "@type": "Machine",
  "identifier": "RC-01",
  "name": "Robot cell",
  "description": "Robot cell for loading anodised aluminium housings",
  "customer": "Example GmbH",
  "properties": {"size": 12}
}
```

### AssemblyGroup and AssemblyInstance
A group is a design, an instance is one placement of it. The instances form the tree of the machine.

`PUT /records/AG-IT-003`
```json
{
  "@type": "AssemblyGroup",
  "identifier": "AG-IT-003",
  "name": "Input tray",
  "description": "Drawer tray that feeds anodised housings to the robot",
  "definedIn": "RC-01",
  "properties": {"sizeX": 0.8, "sizeY": 0.6, "sizeZ": 0.2}
}
```
`PUT /records/AG-IT-003-01`
```json
{
  "@type": "AssemblyGroup",
  "identifier": "AG-IT-003-01",
  "name": "Drawer slide",
  "definedIn": "RC-01"
}
```
`PUT /records/AI-1`, the root instance (one per machine)
```json
{
  "@type": "AssemblyInstance",
  "name": "AG-IT-003:1",
  "instanceOf": "AG-IT-003",
  "rootOf": "RC-01",
  "properties": {"path": "AG-IT-003:1"}
}
```
`PUT /records/AI-2`, same for `AI-3` with `AG-IT-003-01:2`
```json
{
  "@type": "AssemblyInstance",
  "name": "AG-IT-003-01:1",
  "instanceOf": "AG-IT-003-01",
  "partOf": "AI-1",
  "properties": {"path": "AG-IT-003:1/AG-IT-003-01:1"}
}
```

### CadFile
`PUT /records/CF-RC-01`
```json
{
  "@type": "CadFile",
  "name": "RC-01.step",
  "format": "STEP",
  "timestamp": "2026-11-06T18:00:00Z",
  "partOf": "RC-01"
}
```
`POST /records/CF-RC-01/upload-form`
```json
{"size": 1048576}
```
After upload: `POST /records/CF-RC-01/complete`.

### KnowledgeItem
`PUT /records/KI-1`
```json
{
  "@type": "KnowledgeItem",
  "itemType": "lesson learned",
  "reference": "Walkthrough RC-01",
  "properties": {
    "name": "Nest chamfer for anodised parts",
    "statement": "Chamfer the nest edges, anodised parts jam on sharp edges.",
    "reasoning": "The anodised layer scratches and the part tilts in the nest.",
    "consequence": "Parts jam and the cell stops.",
    "recommendation": "0.5 mm chamfer on all nest edges.",
    "confidence": "established practice"
  },
  "appliesTo": ["AG-IT-003-01"]
}
```
`PUT /records/KI-2`
```json
{
  "@type": "KnowledgeItem",
  "itemType": "design decision",
  "properties": {
    "name": "Drawer feeding instead of a conveyor",
    "statement": "The cell is fed by drawers, not by a conveyor.",
    "reasoning": "Small batches; the operator refills one drawer while the robot empties the other.",
    "condition": "Batches below 500 parts per shift."
  },
  "appliesTo": ["AG-IT-003"],
  "appliesToMachine": ["RC-01"]
}
```
`PUT /records/KI-3`, about one placement only
```json
{
  "@type": "KnowledgeItem",
  "itemType": "lesson learned",
  "properties": {
    "name": "Left drawer slide hits the fence",
    "statement": "The left slide touches the safety fence when fully open."
  },
  "appliesToInstance": ["AI-2"]
}
```

### Guideline
`PUT /records/GL-1`
```json
{
  "@type": "Guideline",
  "description": "Above 3 m width, transport becomes very expensive.",
  "reference": "Logistics handbook"
}
```

### Misc
- `PATCH /records/AG-IT-003` JSON Merge Patch with given body. Key by key, links and lists replaced as a whole.
- `GET /records?cls=Machine&include=status,children`: machines with their upload status and direct children.
- `GET /records?parentId=AG-IT-003`: records linking to `AG-IT-003`.
- `GET /records/RC-01/tree`: tree from root.
- `GET /records/KI-1/ancestors`: up to the root.
- `DELETE /records/AI-1`: deletes `AI-1`, `AI-2` and `AI-3`, `KI-3` marked for review.
- `DELETE /records/AG-IT-003-01`: its instances `AI-2` and `AI-3` stay in the tree without `instanceOf`, `KI-1` marked for review.
- `GET /records/review`: every record maker for review.
