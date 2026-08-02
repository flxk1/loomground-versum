"""Duplicate-identity audit (scripts/operations/dedupe_audit.py).

One canonical URN, many files: the audit must find every such family, pick the
base copy as keeper, respect curated (sidecar-paired) members, refuse stale
state, quarantine instead of delete, and hand the removals to the sanctioned
sync path.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

import versum.profiles  # noqa: F401 — register built-in profiles
from versum import sync

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "operations" / "dedupe_audit.py"
_spec = importlib.util.spec_from_file_location("dedupe_audit", _SCRIPT)
da = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(da)

DOC_ALPHA = "A widget is defined as a small thing. A widget causes value in the market.\n"
DOC_BETA = "A gadget is defined as a device. A gadget causes noise in the room.\n"


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _sidecar(for_file: Path, canonical_urn: str) -> None:
    _write(for_file.with_name(for_file.name + ".metadata.json"),
           json.dumps({"canonical_urn": canonical_urn, "title": for_file.stem}))


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


def _dup_corpus(tmp_path: Path) -> tuple[dict, Path]:
    """Two curated files sharing one URN, plus an unrelated singleton."""
    cfg = _config(tmp_path)
    lib = Path(cfg["libraries"][0]["root_path"])
    for name in ("a.txt", "a-copy.txt"):
        _write(lib / "alpha" / name, DOC_ALPHA)
        _sidecar(lib / "alpha" / name, "urn:test:dup")
    _write(lib / "beta" / "unique.txt", DOC_BETA)
    _sidecar(lib / "beta" / "unique.txt", "urn:test:solo")
    sync.sync_once(cfg)
    return cfg, lib


def test_audit_finds_family_and_protects_curated_members(tmp_path):
    cfg, lib = _dup_corpus(tmp_path)
    report = da.audit(cfg)
    result = report["libraries"][0]
    assert result["duplicate_families"] == 1
    fam = result["families"][0]
    assert fam["canonical_urn"] == "urn:test:dup"
    assert fam["keeper"] == "alpha/a.txt"          # shortest relpath wins
    member = fam["members"][0]
    assert member["relpath"] == "alpha/a-copy.txt"
    assert member["byte_identical_to_keeper"] and member["curated"]
    assert result["claims_double_counted"] == member["n_claims"] > 0
    assert result["moves_planned"] == [] and result["skipped_curated"] == 1
    assert (lib / "alpha" / "a-copy.txt").exists()  # read-only: nothing moved


def test_quarantine_moves_pair_and_sync_drops_exactly_its_rows(tmp_path):
    cfg, lib = _dup_corpus(tmp_path)
    quarantine = tmp_path / "quarantine"
    report = da.audit(cfg, include_curated=True)
    assert report["libraries"][0]["moves_planned"] == ["alpha/a-copy.txt"]

    moved = da.apply_moves(cfg, report, quarantine)
    assert moved == 1
    assert (quarantine / "lib" / "alpha" / "a-copy.txt").exists()
    assert (quarantine / "lib" / "alpha" / "a-copy.txt.metadata.json").exists()
    assert not (lib / "alpha" / "a-copy.txt").exists()

    r = sync.sync_once(cfg)
    assert (r["new"], r["changed"], r["removed"], r["errors"]) == (0, 0, 1, 0)
    state = sync.SyncState(cfg["kg_root"])
    assert state.get("lib", "alpha/a-copy.txt") is None
    assert state.get("lib", "alpha/a.txt")["canonical_urn"] == "urn:test:dup"
    assert da.audit(cfg)["libraries"][0]["duplicate_families"] == 0


def test_stale_family_plans_no_moves(tmp_path):
    cfg, lib = _dup_corpus(tmp_path)
    (lib / "alpha" / "a-copy.txt").unlink()        # disk moved on without a sync
    report = da.audit(cfg, include_curated=True)
    result = report["libraries"][0]
    assert result["stale_families"] == 1
    assert result["moves_planned"] == []


def test_quarantine_inside_library_is_refused(tmp_path):
    cfg, lib = _dup_corpus(tmp_path)
    report = da.audit(cfg, include_curated=True)
    with pytest.raises(SystemExit, match="re-index"):
        da.apply_moves(cfg, report, lib / "quarantine")
    assert (lib / "alpha" / "a-copy.txt").exists()  # refused before any move
    da.apply_moves(cfg, da.audit(cfg, include_curated=True), lib / "_quarantine")
    assert (lib / "_quarantine" / "lib" / "alpha" / "a-copy.txt").exists()
