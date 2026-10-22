"""Generate CycloneDX SBOMs for the API and web applications.

The inventories are derived from the committed lockfiles:

* ``apps/api/uv.lock`` -> ``Documentation/sbom/api.cdx.json``
* ``apps/web/package-lock.json`` -> ``Documentation/sbom/web.cdx.json``

Run without arguments to write the files, with ``--check`` to verify that the
committed files are up to date (used by CI and by the pre-commit hook).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "Documentation" / "sbom"

API_DIR = ROOT / "apps" / "api"
WEB_DIR = ROOT / "apps" / "web"

SPEC_VERSION = "1.5"
GENERATOR = {"vendor": "amos2026ws02", "name": "generate-sbom", "version": "1.0.0"}


def run(command: list[str], cwd: Path) -> str:
    executable = shutil.which(command[0])
    if executable is None:
        raise SystemExit(f"Required tool not found: {command[0]}")

    result = subprocess.run(
        [executable, *command[1:]],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def normalize_pypi_name(name: str) -> str:
    return name.lower().replace("_", "-")


def sha256_entries(*artifacts: Any) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for artifact in artifacts:
        if not artifact:
            continue
        digest = artifact.get("hash", "")
        if not digest.startswith("sha256:"):
            continue
        entries.append({"alg": "SHA-256", "content": digest.split(":", 1)[1]})
    return entries


def build_api_sbom() -> dict[str, Any]:
    """Build the API SBOM from the uv lockfile."""
    # The inventory is only trustworthy if the lockfile matches pyproject.toml.
    try:
        run(["uv", "lock", "--check", "--project", str(API_DIR)], ROOT)
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            "apps/api/uv.lock is out of date. Run: uv lock --directory apps/api"
        ) from error

    lock = tomllib.loads((API_DIR / "uv.lock").read_text(encoding="utf-8"))
    packages = lock.get("package", [])

    root: dict[str, Any] | None = None
    components: list[dict[str, Any]] = []
    depends: list[dict[str, Any]] = []

    for package in packages:
        name = package["name"]
        version = package.get("version", "")
        source = package.get("source", {})

        if "editable" in source or "virtual" in source:
            root = package
            continue

        purl = f"pkg:pypi/{normalize_pypi_name(name)}@{version}"
        component: dict[str, Any] = {
            "bom-ref": purl,
            "type": "library",
            "name": name,
            "version": version,
            "purl": purl,
        }
        hashes = sha256_entries(package.get("sdist"), *(package.get("wheels") or []))
        if hashes:
            component["hashes"] = hashes
        components.append(component)

        depends.append(
            {
                "ref": purl,
                "dependsOn": [
                    f"pkg:pypi/{normalize_pypi_name(dep['name'])}@"
                    f"{_version_of(packages, dep['name'])}"
                    for dep in package.get("dependencies", [])
                ],
            }
        )

    if root is None:
        raise SystemExit(f"No root package found in {API_DIR / 'uv.lock'}")

    root_ref = f"{root['name']}@{root.get('version', '')}"
    root_component = {
        "bom-ref": root_ref,
        "type": "application",
        "name": root["name"],
        "version": root.get("version", ""),
    }

    components.sort(key=lambda item: (item["name"], item["version"]))
    depends.sort(key=lambda item: item["ref"])

    return {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "version": 1,
        "metadata": {
            "tools": [GENERATOR],
            "component": root_component,
        },
        "components": components,
        "dependencies": [
            {
                "ref": root_ref,
                "dependsOn": [
                    f"pkg:pypi/{normalize_pypi_name(dep['name'])}@"
                    f"{_version_of(packages, dep['name'])}"
                    for dep in root.get("dependencies", [])
                ],
            },
            *depends,
        ],
    }


def _version_of(packages: list[dict[str, Any]], name: str) -> str:
    for package in packages:
        if package["name"] == name:
            return package.get("version", "")
    return ""


def build_web_sbom() -> dict[str, Any]:
    """Build the web SBOM from the npm lockfile."""
    raw = run(
        [
            "npm",
            "sbom",
            "--sbom-format",
            "cyclonedx",
            "--sbom-type",
            "application",
            "--package-lock-only",
            "--include=dev",
            "--include=optional",
            "--include=peer",
        ],
        WEB_DIR,
    )
    document = json.loads(raw)

    # Generation-time metadata would change on every run.
    document.pop("serialNumber", None)
    document.get("metadata", {}).pop("timestamp", None)

    components = document.get("components", [])
    components.sort(key=lambda item: (item.get("name", ""), item.get("version", "")))
    dependencies = document.get("dependencies", [])
    dependencies.sort(key=lambda item: item.get("ref", ""))

    return document


def serialize(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


TARGETS = [
    ("api.cdx.json", build_api_sbom),
    ("web.cdx.json", build_web_sbom),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed SBOMs differ from the generated ones.",
    )
    args = parser.parse_args()

    outdated: list[str] = []

    for filename, builder in TARGETS:
        content = serialize(builder())
        destination = OUTPUT / filename
        current = (
            destination.read_text(encoding="utf-8") if destination.exists() else None
        )

        if current == content:
            continue

        relative = destination.relative_to(ROOT)
        if args.check:
            outdated.append(str(relative))
        else:
            OUTPUT.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
            print(f"Updated {relative}")

    if outdated:
        raise SystemExit(
            "SBOMs are missing or outdated:\n"
            + "\n".join(outdated)
            + "\nRun: python scripts/generate_sbom.py"
        )


if __name__ == "__main__":
    sys.exit(main())
