# Software Bill of Materials

CycloneDX 1.5 inventories for the application dependencies of this repository.

| File             | Source of truth                    | Contents                                       |
| ---------------- | ---------------------------------- | ---------------------------------------------- |
| `api.cdx.json`   | `apps/api/uv.lock`                 | Python packages resolved for the API            |
| `web.cdx.json`   | `apps/web/package-lock.json`       | npm packages resolved for the frontend          |

## Regeneration

The files are generated, not edited by hand:

```bash
uv run --project apps/api python scripts/generate_sbom.py            # write the inventories
uv run --project apps/api python scripts/generate_sbom.py --check    # fail if the committed files are stale
uv run --project apps/api python scripts/generate_sbom.py --staged   # fail if the staged files are stale
```

A pre-commit hook runs the `--staged` variant whenever dependency inputs change: it compares the inventories staged for the commit against freshly generated ones and blocks the commit if they differ. The CI workflow `sbom-check` runs the `--check` variant and fails the build on stale inventories.

## Pre-commit hook

Run this once after cloning the repository:

```bash
uv tool install pre-commit
pre-commit install
```

The hook requires uv and npm on your `PATH`; uv provides the pinned Python. It only runs when `apps/api/pyproject.toml`, `apps/api/uv.lock`, `apps/web/package.json`, `apps/web/package-lock.json`, the generator script, or the SBOM files themselves are staged.

If the staged SBOMs are missing or outdated, the commit stops and nothing is committed. Regenerate the files, review them, stage them, and commit again:

```bash
uv run --project apps/api python scripts/generate_sbom.py
git diff -- Documentation/sbom/
git add Documentation/sbom/
git commit -m "Update dependencies and SBOMs"
```

## Tool versions

Use the same uv and npm versions locally and in CI: npm records its generator version in the SBOM, so a different npm version yields a different file. Each version has one source of truth:

| Tool   | Source of truth                                   | Also pinned in                                 |
| ------ | ------------------------------------------------- | ---------------------------------------------- |
| Python | `requires-python` in `apps/api/pyproject.toml`    | `sbom-check` workflow, `apps/api/Dockerfile`   |
| uv     | `required-version` in `apps/api/pyproject.toml`   | `sbom-check` workflow, `apps/api/Dockerfile`   |
| npm    | `packageManager` in `apps/web/package.json`       | `sbom-check` workflow                          |
| Node   | `node-version` in the `sbom-check` workflow       | `apps/web/Dockerfile`                          |

`scripts/check_tool_versions.py` fails if any of these disagree, or if `apps/api/Dockerfile` stops installing with `--no-dev` (the API SBOM only covers non-dev dependencies); it runs as a pre-commit hook and in CI. The generator also refuses to run with a local npm that differs from `packageManager`. To bump a version, update every place in its row.

## Underlying commands

The frontend inventory comes straight from npm:

```bash
cd apps/web
npm sbom --sbom-format cyclonedx --sbom-type application --package-lock-only \
  --include=dev --include=optional --include=peer
```

The Python inventory comes straight from uv (0.13.5, pinned via `required-version` in `apps/api/pyproject.toml`):

```bash
uv export --locked --format cyclonedx1.5 --preview-features sbom-export --directory apps/api
```

`--locked` fails if `uv.lock` does not match `pyproject.toml`, so a stale lockfile cannot produce an SBOM.

## Scope

These are application-package inventories. They do not inventory the operating-system packages of the Docker images or the complete Nginx image.

The generation timestamp and the document serial number are removed so that regenerating without dependency changes produces an empty diff.
