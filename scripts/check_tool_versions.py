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

# Each pattern captures the pinned version in its first group.
UV_WORKFLOW_PATTERN = r"setup-uv@.*\n\s+with:\n\s+version:\s*\"?([\d.]+)"
UV_DOCKERFILE_PATTERN = r"ghcr\.io/astral-sh/uv:([\d.]+)"
NPM_WORKFLOW_PATTERN = r"npm install -g npm@([\d.]+)"
NODE_WORKFLOW_PATTERN = r"node-version:\s*\"?([\d.]+)"
NODE_DOCKERFILE_PATTERN = r"FROM node:([\d.]+)"


def label(path: Path) -> str:
    return str(path.relative_to(ROOT))


def search(path: Path, pattern: str) -> str | None:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else None


def uv_versions() -> dict[str, str | None]:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    required = pyproject.get("tool", {}).get("uv", {}).get("required-version", "")
    return {
        label(PYPROJECT): required.removeprefix("==") or None,
        label(WORKFLOW): search(WORKFLOW, UV_WORKFLOW_PATTERN),
        label(API_DOCKERFILE): search(API_DOCKERFILE, UV_DOCKERFILE_PATTERN),
    }


def npm_versions() -> dict[str, str | None]:
    return {
        label(PACKAGE_JSON): npm_package_manager_version(),
        label(WORKFLOW): search(WORKFLOW, NPM_WORKFLOW_PATTERN),
    }


def node_versions() -> dict[str, str | None]:
    return {
        label(WORKFLOW): search(WORKFLOW, NODE_WORKFLOW_PATTERN),
        label(WEB_DOCKERFILE): search(WEB_DOCKERFILE, NODE_DOCKERFILE_PATTERN),
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
