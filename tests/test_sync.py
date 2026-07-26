"""Live Index — real incremental sync of a library into the by-domain KG store.

Uses a temp kg_root + a temp library of a couple of .txt files and a tiny registry CSV,
and asserts the product behaviours end to end (no stubs, no mocks):

  (a) seed_state marks all current files done → next sync_once reports new=0;
  (b) after seeding, ADD a file → sync_once indexes exactly 1; its claims land in
      by-domain/<domain>/claims.csv keyed on the reused/minted canonical_urn; state grows by 1;
  (c) reuse → a file whose relpath/filename matches a registry row reuses that
      canonical_urn with provenance 'kg-registry';
  (d) idempotent → sync_once twice with no change: 2nd reports new=0/changed=0 and the KG
      bytes are byte-for-byte unchanged;
  (e) change → editing a file re-indexes it; its prior rows for that relpath are REPLACED
      (no duplicate canonical rows) and other sources are untouched;
  (f) exclude_prefixes → a top-level '_dupes' folder is skipped.
"""
import csv
import json
from pathlib import Path

import pytest

import versum.profiles  # noqa: F401 — register built-in profiles
from versum import sync


# ── fixtures ─────────────────────────────────────────────────────
REG_CANON = "urn:kg:doc:reused-canonical-42"


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _registry_csv(path: Path) -> None:
    """A tiny KG-shaped source_registry.csv with one row (relpath alpha/reused.txt)."""
    from versum.io.consume import REGISTRY_COLUMNS
    row = {c: "" for c in REGISTRY_COLUMNS}
    row.update({
        "source_id": "s1", "canonical_urn": REG_CANON, "version_urn": REG_CANON + ":v1",
        "original_path": "knowledge_library/alpha/reused.txt", "filename": "reused.txt",
        "extension": ".txt", "detected_year": "2021", "primary_topic": "widgets",
        "topics": "widgets", "jurisdiction": "EU",
    })
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=REGISTRY_COLUMNS)
        w.writeheader()
        w.writerow(row)


def _config(tmp_path: Path, with_registry: bool = True) -> dict:
    kg_root = tmp_path / "kg"
    lib_root = tmp_path / "lib"
    lib_root.mkdir(parents=True, exist_ok=True)
    reg_path = tmp_path / "registry.csv"
    if with_registry:
        _registry_csv(reg_path)
    cfg_path = tmp_path / "config.json"
    cfg = {
        "kg_root": str(kg_root),
        "profile_id": "generic",
        "exclude_prefixes": ["_"],
        "watch_interval_seconds": 5,
        "libraries": [{
            "id": "digital-law",
            "root_path": str(lib_root),
            "urn_namespace": "dls",
            "registry_csv": str(reg_path) if with_registry else None,
            "registry_path_prefix": "knowledge_library/",
        }],
    }
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    return sync.load_config(cfg_path)


def _claims_rows(kg_root: Path, domain: str) -> list[dict]:
    p = Path(kg_root) / "by-domain" / domain / "claims.csv"
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _kg_bytes(kg_root: Path) -> dict:
    """Snapshot the by-domain KG store as raw bytes (the state file is excluded)."""
    base = Path(kg_root) / "by-domain"
    if not base.exists():
        return {}
    return {p.relative_to(base).as_posix(): p.read_bytes()
            for p in sorted(base.rglob("*")) if p.is_file()}


# ── a claim-bearing document (matches the generic profile's markers) ──
DOC_ALPHA = "A widget is defined as a small thing. A widget causes value in the market.\n"
DOC_BETA = "A gadget is defined as a device. A gadget causes noise in the room.\n"
DOC_GAMMA = "A sprocket is defined as a wheel. A sprocket causes motion in a gear.\n"


# ── (a) seed then sync = nothing new ─────────────────────────────
def test_seed_then_sync_is_current(tmp_path):
    cfg = _config(tmp_path)
    lib = Path(cfg["libraries"][0]["root_path"])
    _write(lib / "alpha" / "reused.txt", DOC_ALPHA)
    _write(lib / "beta" / "minted.txt", DOC_BETA)

    seeded = sync.seed_state(cfg)
    assert seeded["total"] == 2

    r = sync.sync_once(cfg)
    assert r["new"] == 0
    assert r["changed"] == 0
    assert r["indexed"] == 0
    # seeding indexed nothing → the by-domain store was never created
    assert _kg_bytes(Path(cfg["kg_root"])) == {}


# ── (b) add one file after seeding → exactly one indexed ─────────
def test_add_after_seed_indexes_one(tmp_path):
    cfg = _config(tmp_path)
    lib = Path(cfg["libraries"][0]["root_path"])
    _write(lib / "alpha" / "reused.txt", DOC_ALPHA)
    sync.seed_state(cfg)

    state_before = sync.SyncState(cfg["kg_root"])
    n_before = len(state_before.files)

    # add a brand new file under a new domain
    _write(lib / "beta" / "fresh.txt", DOC_BETA)
    r = sync.sync_once(cfg)
    assert r["new"] == 1
    assert r["indexed"] == 1
    assert r["claims"] >= 1

    rows = _claims_rows(cfg["kg_root"], "beta")
    assert rows, "the added file's claims must appear in by-domain/beta/claims.csv"
    canon = rows[0]["canonical_urn"]
    assert canon and all(row["canonical_urn"] == canon for row in rows)
    assert all(row["source_urn"] == canon for row in rows)  # keyed on the canonical urn
    assert rows[0]["library"] == "digital-law"

    state_after = sync.SyncState(cfg["kg_root"])
    assert len(state_after.files) == n_before + 1


# ── (c) registry reuse → canonical_urn + provenance kg-registry ──
def test_registry_reuse(tmp_path):
    cfg = _config(tmp_path, with_registry=True)
    lib = Path(cfg["libraries"][0]["root_path"])
    _write(lib / "alpha" / "reused.txt", DOC_ALPHA)   # matches the registry row

    r = sync.sync_once(cfg)
    assert r["reuse"] == 1
    assert r["mint"] == 0

    rows = _claims_rows(cfg["kg_root"], "alpha")
    assert rows and all(row["canonical_urn"] == REG_CANON for row in rows)

    # sources.csv records provenance kg-registry for the reused file
    src = Path(cfg["kg_root"]) / "by-domain" / "alpha" / "sources.csv"
    with open(src, newline="", encoding="utf-8") as fh:
        srows = list(csv.DictReader(fh))
    hit = [s for s in srows if s["path"] == "alpha/reused.txt"]
    assert hit and hit[0]["provenance"] == "kg-registry"
    assert hit[0]["canonical_urn"] == REG_CANON

    # a file with no registry row MINTS under the library namespace (provenance minted)
    _write(lib / "beta" / "minted.txt", DOC_BETA)
    r2 = sync.sync_once(cfg)
    assert r2["reuse"] == 0 and r2["mint"] == 1
    brows = _claims_rows(cfg["kg_root"], "beta")
    assert brows and brows[0]["canonical_urn"].startswith("urn:dls:")


# ── (d) idempotent → second pass writes nothing ──────────────────
def test_idempotent_no_change(tmp_path):
    cfg = _config(tmp_path)
    lib = Path(cfg["libraries"][0]["root_path"])
    _write(lib / "alpha" / "reused.txt", DOC_ALPHA)
    _write(lib / "beta" / "minted.txt", DOC_BETA)

    sync.sync_once(cfg)
    before = _kg_bytes(Path(cfg["kg_root"]))
    r2 = sync.sync_once(cfg)
    after = _kg_bytes(Path(cfg["kg_root"]))

    assert r2["new"] == 0 and r2["changed"] == 0 and r2["indexed"] == 0
    assert before == after, "a no-change pass must leave the KG bytes identical"


# ── (e) change a file → its rows are replaced, others untouched ──
def test_change_replaces_own_rows(tmp_path):
    cfg = _config(tmp_path)
    lib = Path(cfg["libraries"][0]["root_path"])
    reused = lib / "alpha" / "reused.txt"
    other = lib / "beta" / "minted.txt"
    _write(reused, DOC_ALPHA)
    _write(other, DOC_BETA)
    sync.sync_once(cfg)

    beta_before = _claims_rows(cfg["kg_root"], "beta")
    alpha_rows_before = _claims_rows(cfg["kg_root"], "alpha")
    n_alpha_before = len(alpha_rows_before)
    canon = alpha_rows_before[0]["canonical_urn"]

    # bump mtime deterministically forward and change content
    st = reused.stat()
    _write(reused, DOC_ALPHA + DOC_GAMMA)   # add a second claim-bearing pair
    import os
    os.utime(reused, (st.st_mtime + 10, st.st_mtime + 10))

    r = sync.sync_once(cfg)
    assert r["changed"] == 1 and r["indexed"] == 1

    alpha_rows_after = _claims_rows(cfg["kg_root"], "alpha")
    # exactly one canonical key present for this source — no duplicate accumulation
    assert {row["canonical_urn"] for row in alpha_rows_after} == {canon}
    assert len(alpha_rows_after) > n_alpha_before  # the added text produced more claims
    # the other domain's rows are byte-identical — a change never touches other sources
    assert _claims_rows(cfg["kg_root"], "beta") == beta_before


# ── (f) exclude_prefixes → a top-level _dupes folder is skipped ──
def test_exclude_prefixes(tmp_path):
    cfg = _config(tmp_path)
    lib = Path(cfg["libraries"][0]["root_path"])
    _write(lib / "alpha" / "keep.txt", DOC_ALPHA)
    _write(lib / "_dupes" / "skip.txt", DOC_BETA)     # excluded (top-level '_' prefix)

    r = sync.sync_once(cfg)
    assert r["indexed"] == 1  # only alpha/keep.txt

    state = sync.SyncState(cfg["kg_root"])
    keys = list(state.files)
    assert any("alpha/keep.txt" in k for k in keys)
    assert not any("_dupes" in k for k in keys)
    # no by-domain/_dupes store was created
    assert not (Path(cfg["kg_root"]) / "by-domain" / "_dupes").exists()
