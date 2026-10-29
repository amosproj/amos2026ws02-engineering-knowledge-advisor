"""Generate CycloneDX SBOMs for the API and web applications.

The inventories are derived from the committed lockfiles:

* ``apps/api/uv.lock`` -> ``Documentation/sbom/api.cdx.json``
* ``apps/web/package-lock.json`` -> ``Documentation/sbom/web.cdx.json``

The API inventory is enriched with license information read from the package
metadata of the locked wheels, because ``uv export`` does not emit licenses.

Run without arguments to write the files, with ``--check`` to verify that the
committed files are up to date (used by CI), and with ``--staged`` to verify
that the files staged for a commit are up to date (used by the pre-commit
hook).
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
import tempfile
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

API_SBOM_FILE = "api.cdx.json"
WEB_SBOM_FILE = "web.cdx.json"

# License metadata is read from wheels resolved for the API container runtime
# (python:3.13-slim on Linux), so platform-specific packages such as uvloop are
# covered regardless of the machine running the generator.
API_PYTHON_VERSION_FILE = API_DIR / ".python-version"
API_PYTHON_PLATFORM = "linux"

# Free-text ``License`` fields that unambiguously name one SPDX license.
LICENSE_TEXT_TO_SPDX = {
    "apache-2.0": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "isc": "ISC",
    "lgpl-3.0-only": "LGPL-3.0-only",
    "mit": "MIT",
    "mit license": "MIT",
    "mpl-2.0": "MPL-2.0",
    "psf-2.0": "PSF-2.0",
}

# Trove classifiers that unambiguously name one SPDX license. "BSD License" is
# deliberately missing: it does not say which BSD variant applies.
CLASSIFIER_TO_SPDX = {
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
}

# Packages whose metadata is ambiguous or incomplete, checked against the
# license files shipped with the package. Review these on version bumps.
LICENSE_OVERRIDES = {
    # Metadata says "Dual License" with a generic BSD classifier; the LICENSE
    # file applies Apache-2.0 to newer contributions and BSD-3-Clause to all.
    "python-dateutil": "Apache-2.0 AND BSD-3-Clause",
    # Ships LICENSE-APACHE and LICENSE-MIT, but the License field names only MIT.
    "uvloop": "Apache-2.0 OR MIT",
}

SPDX_ID = re.compile(r"^[A-Za-z0-9.+-]+$")


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
    # --no-dev keeps the SBOM aligned with the Dockerfile, dev tools are not shipped.
    try:
        raw = run(
            [
                "uv",
                "export",
                "--locked",
                "--no-dev",
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

    document = json.loads(raw)
    add_api_licenses(document)
    return normalize(document)


def canonical_name(name: str) -> str:
    """Normalize a Python package name as specified by PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_requirements(components: list[dict[str, Any]]) -> str:
    """Pin every component to its locked version and artifact hashes."""
    lines = []
    for component in components:
        hashes = sorted(
            {
                f"--hash=sha256:{item['content']}"
                for reference in component.get("externalReferences", [])
                for item in reference.get("hashes", [])
                if item.get("alg") == "SHA-256"
            }
        )
        lines.append(
            " ".join([f"{component['name']}=={component['version']}", *hashes])
        )
    return "\n".join(lines) + "\n"


def read_package_metadata(
    components: list[dict[str, Any]],
) -> dict[str, importlib.metadata.PackageMetadata]:
    """Install the locked artifacts into a temporary directory and read them."""
    python_version = API_PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()

    with tempfile.TemporaryDirectory() as temp_dir:
        requirements = Path(temp_dir) / "requirements.txt"
        requirements.write_text(locked_requirements(components), encoding="utf-8")
        target = Path(temp_dir) / "site-packages"

        # --no-deps installs exactly the locked set, including packages whose
        # environment markers exclude them on the target platform (tzdata).
        try:
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--quiet",
                    "--no-deps",
                    "--require-hashes",
                    "--target",
                    str(target),
                    "--python-version",
                    python_version,
                    "--python-platform",
                    API_PYTHON_PLATFORM,
                    "--requirement",
                    str(requirements),
                ],
                ROOT,
            )
        except subprocess.CalledProcessError as error:
            raise SystemExit(
                f"Reading API package metadata failed:\n{error.stderr}"
            ) from error

        return {
            canonical_name(distribution.metadata["Name"]): distribution.metadata
            for distribution in importlib.metadata.distributions(path=[str(target)])
        }


def resolve_license(
    name: str, metadata: importlib.metadata.PackageMetadata | None
) -> str | None:
    """Return an SPDX license expression for a package, or None if unknown."""
    if name in LICENSE_OVERRIDES:
        return LICENSE_OVERRIDES[name]
    if metadata is None:
        return None

    # PEP 639 field: already a validated SPDX expression.
    expression = metadata.get("License-Expression")
    if expression:
        return expression.strip()

    text = " ".join((metadata.get("License") or "").split()).lower()
    if text in LICENSE_TEXT_TO_SPDX:
        return LICENSE_TEXT_TO_SPDX[text]

    classifiers = [
        classifier
        for classifier in metadata.get_all("Classifier") or []
        if classifier.startswith("License ::")
    ]
    # Several license classifiers do not say whether they combine with AND or OR.
    if len(classifiers) == 1 and classifiers[0] in CLASSIFIER_TO_SPDX:
        return CLASSIFIER_TO_SPDX[classifiers[0]]

    return None


def license_entry(expression: str) -> dict[str, Any]:
    """Format an SPDX expression as a CycloneDX license choice."""
    if SPDX_ID.match(expression):
        return {"license": {"id": expression}}
    return {"expression": expression}


def add_api_licenses(document: dict[str, Any]) -> None:
    """Attach licenses to the API components, which uv export leaves out."""
    components = document.get("components", [])
    metadata = read_package_metadata(components)

    unresolved = []
    for component in components:
        name = canonical_name(component["name"])
        expression = resolve_license(name, metadata.get(name))
        if expression is None:
            unresolved.append(f"{component['name']}=={component['version']}")
            continue
        component["licenses"] = [license_entry(expression)]

    if unresolved:
        print(
            "Warning: no license found for: "
            + ", ".join(unresolved)
            + ". Add an entry to LICENSE_OVERRIDES in scripts/generate_sbom.py.",
            file=sys.stderr,
        )


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


def index_content(relative: str) -> str | None:
    """Return the content of a file as staged in the git index, if present."""
    # `git show :<path>` rejects backslashes
    result = subprocess.run(
        ["git", "show", f":{Path(relative).as_posix()}"],
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
    TARGETS = [
        (API_SBOM_FILE, build_api_sbom),
        (WEB_SBOM_FILE, build_web_sbom),
    ]
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
                + "\nRun: uv run --project apps/api python scripts/generate_sbom.py"
                + "\nThen: git add Documentation/sbom/"
                + "\nAnd commit again."
            )
        raise SystemExit(
            "SBOMs are missing or outdated:\n"
            + "\n".join(outdated)
            + "\nRun: uv run --project apps/api python scripts/generate_sbom.py"
        )


if __name__ == "__main__":
    main()
