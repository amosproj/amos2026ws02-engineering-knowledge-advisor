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
