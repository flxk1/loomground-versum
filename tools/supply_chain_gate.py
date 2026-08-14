#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Deterministic, fail-closed dependency license inventory (stdlib only)."""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE_VERSION = "loomground-supply-chain-gate/2026.07.25.1"
KNOWN = {
    "attrs": "MIT", "cffi": "MIT", "charset-normalizer": "MIT",
    "cryptography": "Apache-2.0 OR BSD-3-Clause", "iniconfig": "MIT",
    "jsonschema": "MIT",
    "jsonschema-specifications": "MIT", "packaging": "Apache-2.0 OR BSD-2-Clause",
    "pdfminer-six": "MIT", "pdfplumber": "MIT", "pillow": "MIT-CMU",
    "pluggy": "MIT", "pycparser": "BSD-3-Clause", "pygments": "BSD-2-Clause",
    "pypdfium2": "Apache-2.0 OR BSD-3-Clause", "pytest": "MIT",
    "referencing": "MIT", "rpds-py": "MIT",
}
ALLOWED = {"Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "ISC",
           "0BSD", "MIT-0", "CC0-1.0", "BlueOak-1.0.0", "Python-2.0",
           "MIT-CMU", "Apache-2.0 OR BSD-2-Clause",
           "Apache-2.0 OR BSD-3-Clause"}


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def own_license(root: Path = ROOT) -> str:
    candidates = [root / "LICENSE", root / "LICENSES" / "Apache-2.0.txt"]
    for path in candidates:
        if path.is_file() and "Apache License" in path.read_text(encoding="utf-8"):
            return "Apache-2.0"
    raise ValueError("missing recognizable Apache-2.0 repository license")


def add(items: dict[str, dict], name: str, version: str, license_id: str, source: str):
    name = norm(name)
    if not license_id:
        license_id = "Apache-2.0" if name.startswith(("loomground-",)) else KNOWN.get(name, "")
    if not license_id:
        raise ValueError(f"unknown or missing license for dependency {name!r}")
    if license_id not in ALLOWED:
        raise ValueError(f"unapproved license {license_id!r} for dependency {name!r}")
    key = f"{name}@{version}"
    if key in items:
        raise ValueError(f"duplicate dependency component {key!r}")
    items[key] = {"name": name, "version": version, "license": license_id, "source": source}


def inventory() -> dict:
    items: dict[str, dict] = {}
    runtime_external: set[str] = set()
    runtime_first_party: set[str] = set()
    release_pins: set[str] = set()
    first_party_vcs: set[str] = set()
    lock = ROOT / "package-lock.json"
    if lock.is_file():
        raw = json.loads(lock.read_text(encoding="utf-8"))
        for path, meta in sorted(raw.get("packages", {}).items()):
            if not path or not path.startswith("node_modules/"):
                continue
            add(items, path.removeprefix("node_modules/"), str(meta.get("version", "")),
                str(meta.get("license", "")), "package-lock.json")
    pyproject = ROOT / "pyproject.toml"
    if pyproject.is_file():
        raw = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        for spec in raw.get("project", {}).get("dependencies", []):
            name = re.split(r"[@<>=!~;\[ ]", spec, maxsplit=1)[0]
            if norm(name).startswith(("loomground-",)):
                runtime_first_party.add(norm(name))
            else:
                runtime_external.add(norm(name))
    for req in (ROOT / "requirements-dev.txt", ROOT / "requirements-release.txt"):
      if req.is_file():
        for line in req.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = re.split(r"\s*@\s*|[<>=!~]", line, maxsplit=1)[0]
            if req.name == "requirements-release.txt":
                version = line[len(name):].strip()
                if not version.startswith("=="):
                    raise ValueError(f"release dependency is not exactly pinned: {line!r}")
                release_pins.add(norm(name))
                add(items, name, version.removeprefix("=="), "", req.name)
            elif norm(name).startswith(("loomground-",)):
                match = re.fullmatch(
                    r"[^ ]+\s*@\s*git\+https://[^ ]+@([0-9a-f]{40})", line)
                if not match:
                    raise ValueError(
                        f"first-party dependency lacks exact 40-char VCS commit: {line!r}")
                first_party_vcs.add(norm(name))
                add(items, name, match.group(1), "", req.name)
            else:
                version = line[len(name):].strip()
                if not version.startswith("=="):
                    raise ValueError(f"development dependency is not exactly pinned: {line!r}")
                add(items, name, version.removeprefix("=="), "", req.name)
    missing_pins = sorted(runtime_external - release_pins)
    extra_pins = sorted(release_pins - runtime_external)
    if missing_pins or extra_pins:
        raise ValueError(
            "requirements-release.txt must exactly resolve external runtime dependencies; "
            f"missing={missing_pins}, extra={extra_pins}")
    missing_vcs = sorted(runtime_first_party - first_party_vcs)
    extra_vcs = sorted(first_party_vcs - runtime_first_party)
    if missing_vcs or extra_vcs:
        raise ValueError(
            "requirements-dev.txt first-party VCS refs must exactly resolve runtime dependencies; "
            f"missing={missing_vcs}, extra={extra_vcs}")
    components = []
    for key in sorted(items):
        item = items[key]
        components.append({
            "type": "library", "name": item["name"], "version": item["version"],
            "licenses": [{"license": {"id": item["license"]}}],
            "properties": [{"name": "loomground:source", "value": item["source"]}],
        })
    return {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "metadata": {
            "tools": {"components": [{"type": "application", "name": GATE_VERSION}]},
            "component": {"type": "application", "name": ROOT.name,
                          "licenses": [{"license": {"id": own_license()}}]},
        },
        "components": components,
    }


def self_test() -> None:
    try:
        add({}, "definitely-unknown", "1", "", "teeth")
    except ValueError:
        pass
    else:
        raise ValueError("unknown-license teeth did not reject")
    with tempfile.TemporaryDirectory() as directory:
        try:
            own_license(Path(directory))
        except ValueError:
            pass
        else:
            raise ValueError("missing-project-license teeth did not reject")
    duplicate: dict[str, dict] = {}
    add(duplicate, "pytest", "9.1.1", "MIT", "teeth")
    try:
        add(duplicate, "pytest", "9.1.1", "MIT", "teeth")
    except ValueError:
        pass
    else:
        raise ValueError("duplicate-component teeth did not reject")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notices", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            print(f"SUPPLY CHAIN SELF-TEST PASS ({GATE_VERSION})")
            return 0
        result = inventory()
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        print(f"SUPPLY CHAIN FAIL: {exc}", file=sys.stderr)
        return 1
    if args.notices:
        print("# Third-party dependency notices\\n")
        for item in result["components"]:
            license_id = item["licenses"][0]["license"]["id"]
            print(f"- {item['name']} {item['version']} — {license_id}")
    else:
        print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
