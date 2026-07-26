"""Guard against the manifest drift that shipped a stale package version.

This repository carries three independent version axes, and this module gates only
one of them:

1. **Package/release** — pyproject.toml's ``version``. What PyPI installs.
2. **Plugin/distribution** — package.json and .claude-plugin/plugin.json's shared
   ``version``. The companion-skill bundle's own version. Versum deliberately
   *aligns* this axis with the package/release axis (both currently 0.6.1), unlike
   sibling repositories that let the two drift independently; the assertions below
   encode that deliberate choice and would need to change if versum ever stopped
   aligning them.
3. **Contract/protocol** — the claim-axes version and other frozen wire contracts
   named in docs/reference/specification.md. Frozen independently of the other two
   axes; this module does not touch it and it must never be asserted equal to
   either version above.

pyproject.toml, package.json, and .claude-plugin/plugin.json each declare this
project's name and version independently. They drifted once — pyproject.toml sat at
0.1.0 while the two plugin manifests had already moved to 0.5.2 — and nothing caught
it before release. package.json and .claude-plugin/plugin.json are a deliberate pair
(the richer package.json also carries the Codex adapter and marketplace fields
`.claude-plugin/plugin.json` doesn't need), consistent with every other repo in this
family, so this does not collapse them into one file; it only pins their shared
fields to move together.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _project_field(name: str) -> str:
    """Read a single-line ``name = "value"`` field from pyproject.toml's [project] table."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(rf'^{name} = "([^"]+)"', text, re.MULTILINE)
    assert match, f"pyproject.toml has no top-level {name!r} field"
    return match.group(1)


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_name_and_version_agree_across_manifests():
    pyproject_name = _project_field("name")
    pyproject_version = _project_field("version")
    package = _load("package.json")
    plugin = _load(".claude-plugin/plugin.json")

    assert pyproject_name == package["name"] == plugin["name"], (
        f"name drift: pyproject.toml={pyproject_name!r} package.json={package['name']!r} "
        f".claude-plugin/plugin.json={plugin['name']!r}")
    assert pyproject_version == package["version"] == plugin["version"], (
        f"version drift: pyproject.toml={pyproject_version!r} "
        f"package.json={package['version']!r} "
        f".claude-plugin/plugin.json={plugin['version']!r}")


def test_package_json_and_plugin_json_agree_on_shared_fields():
    package = _load("package.json")
    plugin = _load(".claude-plugin/plugin.json")
    for field in ("name", "version", "description", "author", "keywords"):
        assert package.get(field) == plugin.get(field), (
            f"{field!r} drift: package.json={package.get(field)!r} "
            f".claude-plugin/plugin.json={plugin.get(field)!r}")
