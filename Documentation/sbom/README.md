# Software Bill of Materials

CycloneDX 1.5 inventories for the application dependencies of this repository.

| File             | Source of truth                    | Contents                                       |
| ---------------- | ---------------------------------- | ---------------------------------------------- |
| `api.cdx.json`   | `apps/api/uv.lock`                 | Python packages resolved for the API            |
| `web.cdx.json`   | `apps/web/package-lock.json`       | npm packages resolved for the frontend          |

## Regeneration

The files are generated, not edited by hand:

```bash
python scripts/generate_sbom.py          # write the inventories
python scripts/generate_sbom.py --check  # fail if the committed files are stale
```

A pre-commit hook runs the generator whenever dependency inputs change. The CI workflow `sbom-check` runs the `--check` variant and fails the build on stale inventories.

Use the same uv and npm versions locally and in CI: npm records its generator version in the SBOM, so a different npm version yields a different file.

## Scope

These are application-package inventories. They do not inventory the operating-system packages of the Docker images or the complete Nginx image.

The generation timestamp and the document serial number are removed so that regenerating without dependency changes produces an empty diff.
