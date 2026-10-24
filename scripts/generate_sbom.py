"""Generate CycloneDX SBOMs for the API and web applications.

The inventories are derived from the committed lockfiles:

* ``apps/api/uv.lock`` -> ``Documentation/sbom/api.cdx.json``
* ``apps/web/package-lock.json`` -> ``Documentation/sbom/web.cdx.json``

Run without arguments to write the files, with ``--check`` to verify that the
committed files are up to date (used by CI), and with ``--staged`` to verify
that the files staged for a commit are up to date (used by the pre-commit
hook).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from check_tool_versions import npm_package_manager_version

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "Documentation" / "sbom"

API_DIR = ROOT / "apps" / "api"
WEB_DIR = ROOT / "apps" / "web"

UV_SBOM_FORMAT = "cyclonedx1.5"
NPM_SBOM_FORMAT = "cyclonedx"
NPM_SBOM_TYPE = "application"


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


def build_api_sbom() -> dict[str, Any]:
    """Build the API SBOM from the uv lockfile."""
    # --locked fails if uv.lock does not match pyproject.toml, so the inventory
    # always reflects the committed dependency set.
    try:
        raw = run(
            [
                "uv",
                "export",
                "--locked",
                "--format",
                UV_SBOM_FORMAT,
                "--preview-features",
                "sbom-export",
                "--quiet",
                "--directory",
                str(API_DIR),
            ],
            ROOT,
        )
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            f"uv export failed:\n{error.stderr}"
            "If apps/api/uv.lock is out of date, run: uv lock --directory apps/api"
        ) from error

    return normalize(json.loads(raw))


def build_web_sbom() -> dict[str, Any]:
    """Build the web SBOM from the npm lockfile."""
    # npm records its own version in the SBOM, so a different local npm would
    # produce a different file than CI.
    expected = npm_package_manager_version()
    actual = run(["npm", "--version"], WEB_DIR).strip()
    if actual != expected:
        raise SystemExit(
            f"npm {expected} is required (packageManager in apps/web/package.json), "
            f"found {actual}. Run: npm install -g npm@{expected}"
        )

    raw = run(
        [
            "npm",
            "sbom",
            "--sbom-format",
            NPM_SBOM_FORMAT,
            "--sbom-type",
            NPM_SBOM_TYPE,
            "--package-lock-only",
            "--include=dev",
            "--include=optional",
            "--include=peer",
        ],
        WEB_DIR,
    )
    return normalize(json.loads(raw))


def normalize(document: dict[str, Any]) -> dict[str, Any]:
    """Make a generated SBOM reproducible across runs."""
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


def index_content(relative: str) -> str | None:
    """Return the content of a file as staged in the git index, if present."""
    result = subprocess.run(
        ["git", "show", f":{relative}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return None
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed SBOMs differ from the generated ones.",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help=(
            "Fail if the staged SBOMs differ from the generated ones. "
            "Used by the pre-commit hook."
        ),
    )
    args = parser.parse_args()

    outdated: list[str] = []

    for filename, builder in TARGETS:
        content = serialize(builder())
        destination = OUTPUT / filename
        relative = str(destination.relative_to(ROOT))

        if args.staged:
            # Compare against the index: that is what the commit will contain.
            # Files that are not tracked at all are reported as missing.
            current = index_content(relative)
        else:
            current = (
                destination.read_text(encoding="utf-8")
                if destination.exists()
                else None
            )

        if current == content:
            continue

        if args.staged or args.check:
            outdated.append(relative)
        else:
            OUTPUT.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
            print(f"Updated {relative}")

    if outdated:
        if args.staged:
            raise SystemExit(
                "SBOMs are missing or outdated in the commit:\n"
                + "\n".join(outdated)
                + "\nRun: python3 scripts/generate_sbom.py"
                + "\nThen: git add Documentation/sbom/"
                + "\nAnd commit again."
            )
        raise SystemExit(
            "SBOMs are missing or outdated:\n"
            + "\n".join(outdated)
            + "\nRun: python3 scripts/generate_sbom.py"
        )


if __name__ == "__main__":
    main()
