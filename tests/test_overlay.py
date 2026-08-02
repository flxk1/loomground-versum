"""The markdown overlay projection: deterministic, self-owned, never corpus."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import versum.profiles  # noqa: F401 — register built-in profiles
from versum import sync
from versum.overlay import write_overlay

DOC_ALPHA = "A widget is defined as a small thing. A widget causes value in the market.\n"
DOC_BETA = "A gadget is defined as a device. A gadget causes noise in the room.\n"


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _config(tmp_path: Path) -> dict:
    kg_root = tmp_path / "kg"
    lib_root = tmp_path / "lib"
    lib_root.mkdir(parents=True, exist_ok=True)
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "kg_root": str(kg_root), "profile_id": "generic",
        "libraries": [{"id": "lib", "root_path": str(lib_root),
                       "urn_namespace": "test", "registry_csv": None}],
    }), encoding="utf-8")
    return sync.load_config(cfg_path)


def _overlay_bytes(lib_root: Path) -> dict[str, bytes]:
    base = lib_root / "_overlay"
    return {p.relative_to(base).as_posix(): p.read_bytes()
            for p in sorted(base.rglob("*")) if p.is_file()}


def test_overlay_renders_identity_and_claim_digest(tmp_path):
    cfg = _config(tmp_path)
    lib = Path(cfg["libraries"][0]["root_path"])
    _write(lib / "alpha" / "a.txt", DOC_ALPHA)
    _write(lib / "beta" / "b.txt", DOC_BETA)
    sync.sync_once(cfg)

    report = write_overlay(cfg)
    assert report["libraries"][0]["sources"] == 2
    assert report["libraries"][0]["domains"] == 2

    note = (lib / "_overlay" / "sources" / "alpha" / "a.txt.md").read_text(encoding="utf-8")
    urn = sync.SyncState(cfg["kg_root"]).get("lib", "alpha/a.txt")["canonical_urn"]
    assert urn in note
    assert "A widget is defined as a small thing." in note
    assert "(../../../alpha/a.txt)" in note  # relative link back to the source file

    index = (lib / "_overlay" / "index.md").read_text(encoding="utf-8")
    assert report["graph_version"] and report["graph_version"] in index
    assert "[alpha](domains/alpha.md)" in index
    assert "a.txt" in (lib / "_overlay" / "domains" / "alpha.md").read_text(encoding="utf-8")


def test_overlay_is_deterministic_and_removes_stale_files(tmp_path):
    cfg = _config(tmp_path)
    lib = Path(cfg["libraries"][0]["root_path"])
    _write(lib / "alpha" / "a.txt", DOC_ALPHA)
    sync.sync_once(cfg)

    write_overlay(cfg)
    before = _overlay_bytes(lib)
    _write(lib / "_overlay" / "sources" / "stale.md", "left over from an older shape\n")

    report = write_overlay(cfg)
    result = report["libraries"][0]
    assert result["removed"] == 1
    assert result["written"] == 0 and result["unchanged"] == len(before)
    assert _overlay_bytes(lib) == before


def test_overlay_is_never_corpus(tmp_path):
    cfg = _config(tmp_path)
    lib = Path(cfg["libraries"][0]["root_path"])
    _write(lib / "alpha" / "a.txt", DOC_ALPHA)
    sync.sync_once(cfg)
    write_overlay(cfg)

    r = sync.sync_once(cfg)
    assert (r["new"], r["changed"], r["removed"], r["errors"]) == (0, 0, 0, 0)
    assert not any("_overlay" in key for key in sync.SyncState(cfg["kg_root"]).files)


def test_overlay_refuses_a_dirname_the_walk_would_index(tmp_path):
    cfg = _config(tmp_path)
    Path(cfg["libraries"][0]["root_path"], "alpha").mkdir(parents=True)
    with pytest.raises(ValueError, match="exclude"):
        write_overlay(cfg, dirname="overlay")
