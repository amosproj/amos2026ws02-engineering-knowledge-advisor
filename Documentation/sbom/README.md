# Software Bill of Materials

CycloneDX 1.5 inventories for the application dependencies of this repository.

| File             | Source of truth                    | Contents                                       |
| ---------------- | ---------------------------------- | ---------------------------------------------- |
| `api.cdx.json`   | `apps/api/uv.lock`                 | Python packages resolved for the API            |
| `web.cdx.json`   | `apps/web/package-lock.json`       | npm packages resolved for the frontend          |

## Regeneration

The files are generated, not edited by hand:

```bash
python3 scripts/generate_sbom.py            # write the inventories
python3 scripts/generate_sbom.py --check    # fail if the committed files are stale
python3 scripts/generate_sbom.py --staged   # fail if the staged files are stale
```

A pre-commit hook runs the `--staged` variant whenever dependency inputs change: it compares the inventories staged for the commit against freshly generated ones and blocks the commit if they differ. The CI workflow `sbom-check` runs the `--check` variant and fails the build on stale inventories.

Use the same uv and npm versions locally and in CI: npm records its generator version in the SBOM, so a different npm version yields a different file.

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
