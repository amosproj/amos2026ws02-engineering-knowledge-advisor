# Engineering Knowledge Advisor API

FastAPI backend. Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

## Configuration

| Variable      | Values        | Default |
|---------------|---------------|---------|
| `API_PROFILE` | `dev`, `prod` | `dev`   |

Settings are read in this order:
1. environment variables (prefix `API_`)
2. `.env`
3. defaults

`.env` is used from the directory the backend is started from:
- start from `apps/api/` => `apps/api/.env`
- start from repository root with `--directory` => `apps/api/.env`
- start from repository root with `--project` => `.env` at root

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

## Background jobs

The `worker` service (`python -m worker`, code in `src/worker/`) runs one loop with three jobs:

| Job | When | What it does |
|-----|------|--------------|
| `process_next_machine` | every 2 s, back to back while machines wait | Takes the machine waiting longest in `processing`, streams its STEP file to compute the SHA-256 and check the `ISO-10303-21;` / `END-ISO-10303-21;` markers, then sets it `ready` or `failed` (`invalid_step_file`, `duplicate_file`, `upload_not_found`). The object of a failed machine is deleted. |
| `expire_abandoned_uploads` | at start, then hourly | Deletes the machines still `uploading` 24 h after their creation, with their object. |
| `delete_orphan_objects` | at start, then hourly | Deletes the objects under `machines/` older than 24 h that no machine points to, or whose machine failed. |

- A machine is locked (`FOR UPDATE SKIP LOCKED`) while it is processed, so several workers can run side by side. If a worker stops or crashes, the lock is released and the machine is processed again.
- On a storage or database error, the machine stays in `processing` and is retried after 30 s.
- The worker touches `/tmp/worker-heartbeat` every 10 s. The container is reported unhealthy when the file is older than one minute.

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
