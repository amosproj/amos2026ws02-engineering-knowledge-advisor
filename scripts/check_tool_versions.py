"""Verify that the pinned uv, npm and Node versions agree across the repository.

The SBOMs are only reproducible when every environment uses the same tool
versions, so each version has one source of truth and every other place that
pins it must match:

* uv: ``required-version`` in ``apps/api/pyproject.toml``
  (also pinned in the SBOM workflow and ``apps/api/Dockerfile``)
* npm: ``packageManager`` in ``apps/web/package.json``
  (also pinned in the SBOM workflow)
* Node: ``node-version`` in the SBOM workflow
  (also pinned in ``apps/web/Dockerfile``)

Used by the pre-commit hook and the CI workflow.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PYPROJECT = ROOT / "apps" / "api" / "pyproject.toml"
PACKAGE_JSON = ROOT / "apps" / "web" / "package.json"
WORKFLOW = ROOT / ".github" / "workflows" / "sbom-check.yml"
API_DOCKERFILE = ROOT / "apps" / "api" / "Dockerfile"
WEB_DOCKERFILE = ROOT / "apps" / "web" / "Dockerfile"


def search(path: Path, pattern: str) -> str | None:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else None


def uv_versions() -> dict[str, str | None]:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    required = pyproject.get("tool", {}).get("uv", {}).get("required-version", "")
    return {
        "apps/api/pyproject.toml": required.removeprefix("==") or None,
        ".github/workflows/sbom-check.yml": search(
            WORKFLOW, r"setup-uv@.*\n\s+with:\n\s+version:\s*\"?([\d.]+)"
        ),
        "apps/api/Dockerfile": search(
            API_DOCKERFILE, r"ghcr\.io/astral-sh/uv:([\d.]+)"
        ),
    }


def npm_versions() -> dict[str, str | None]:
    return {
        "apps/web/package.json": npm_package_manager_version(),
        ".github/workflows/sbom-check.yml": search(
            WORKFLOW, r"npm install -g npm@([\d.]+)"
        ),
    }


def node_versions() -> dict[str, str | None]:
    return {
        ".github/workflows/sbom-check.yml": search(
            WORKFLOW, r"node-version:\s*\"?([\d.]+)"
        ),
        "apps/web/Dockerfile": search(WEB_DOCKERFILE, r"FROM node:([\d.]+)"),
    }


def npm_package_manager_version() -> str | None:
    """Return the npm version pinned by ``packageManager`` in package.json."""
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    name, _, version = package.get("packageManager", "").partition("@")
    return version if name == "npm" and version else None


def main() -> None:
    problems: list[str] = []

    for tool, versions in [
        ("uv", uv_versions()),
        ("npm", npm_versions()),
        ("node", node_versions()),
    ]:
        if None in versions.values() or len(set(versions.values())) != 1:
            lines = "\n".join(
                f"  {path}: {version or 'not found'}"
                for path, version in versions.items()
            )
            problems.append(f"{tool} version mismatch:\n{lines}")

    if problems:
        raise SystemExit("\n".join(problems))

    print("Tool versions match.")


if __name__ == "__main__":
    main()
