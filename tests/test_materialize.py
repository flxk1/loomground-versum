"""Phase 3 loop-7: additive claims-layer materialization keyed on canonical_urn.

Index a small folder against a consume registry (so a source's claims key on the KG's
own ``canonical_urn``, not a minted path-slug), materialize the ``.versum`` semantic layer
into a temp target, and assert:

  * every emitted claim / concept / edge / fingerprint keys on the canonical_urn (never a
    path-slug, never a filename);
  * a source with NO canonical_urn (minted) is SKIPPED with a reported count, not dropped
    silently and not emitted under a path-slug key;
  * the source ``.versum`` store (the KG provenance linkage) is byte-for-byte untouched —
    materialize is additive and REFERENCES the store, it is not a write door into it;
  * a second materialize call on the unchanged folder is a no-op (identical bytes).
"""
import csv
import json
from pathlib import Path

import pytest

from versum.store import graph as g
from versum.io import consume
from versum.store.index import index_folder
from versum.materialize import materialize
import versum.profiles  # noqa: F401 — register built-ins

CANON = "urn:kg:doc:reused-canonical-0001"       # a KG canonical_urn, NOT a path-slug


def _store_bytes(versum_dir: Path) -> dict:
    """Snapshot every file under the .versum store as raw bytes."""
    return {p.relative_to(versum_dir).as_posix(): p.read_bytes()
            for p in sorted(versum_dir.rglob("*")) if p.is_file()}


def _target_bytes(target: Path) -> dict:
    return {p.relative_to(target).as_posix(): p.read_bytes()
            for p in sorted(target.rglob("*")) if p.is_file()}


def _build_indexed_folder(root: Path):
    """Index a folder where ONE file reuses a KG canonical_urn and one MINTS (no canonical)."""
    # the reused source (matched by relpath) — its claims key on CANON
    reg = consume.Registry([{
        "original_path": "sub/note.md", "filename": "note.md",
        "canonical_urn": CANON, "version_urn": CANON + ":v1",
        "primary_topic": "widgets", "topics": "widgets",
        "jurisdiction": "EU", "detected_year": "2021",
    }])
    (root / "sub").mkdir(parents=True, exist_ok=True)
    (root / "sub" / "note.md").write_text(
        "A widget is defined as a thing. A widget causes value.\n", encoding="utf-8")
    # a second file absent from the registry → MINTS (canonical_urn stays empty)
    (root / "orphan.md").write_text(
        "A gadget is defined as a device. A gadget causes noise.\n", encoding="utf-8")
    manifest = index_folder(root, "generic", consume=reg, library="dls-knowledge")
    return manifest


def _curate_a_concept(versum_dir: Path):
    """Simulate a curator writing a concept + a grounds edge from a claim of the reused source."""
    claims = g.load_claims(versum_dir / "claims.csv")
    reused_claim = next(c for c in claims if c["source_urn"] == CANON)
    g.save_concepts(versum_dir / "concepts.csv",
                    [g.Concept("widget", "Widget", "general")])
    g.save_edges(versum_dir / "semantic_edges.csv",
                 [g.Edge("e1", reused_claim["item_id"], "widget", "grounds")])


def test_materialize_keys_every_row_on_canonical_urn(tmp_path):
    folder = tmp_path / "corpus"
    folder.mkdir()
    _build_indexed_folder(folder)
    v = folder / ".versum"
    _curate_a_concept(v)

    target = tmp_path / "kg-layer"
    result = materialize(folder, target, library="dls-knowledge")

    # ── every emitted CLAIM row keys on the canonical_urn (not a path-slug) ──
    claim_rows = list(csv.DictReader(open(target / "claims.csv")))
    assert claim_rows, "no claims materialized"
    for r in claim_rows:
        assert r["canonical_urn"] == CANON
        assert r["library"] == "dls-knowledge"
        assert not r["canonical_urn"].startswith("urn:kg:source:")   # never a path-slug
        assert "note" not in r["canonical_urn"]                      # never the filename
    # the orphan (minted, no canonical) source contributed NO materialized claims …
    assert all(r["canonical_urn"] == CANON for r in claim_rows)
    # … and was skipped with a reported count (not dropped silently)
    assert result["n_claims_skipped_no_canonical"] >= 1
    assert result["n_sources_skipped_no_canonical"] == 1

    # ── every emitted CONCEPT row keys on the canonical_urn ──
    concept_rows = list(csv.DictReader(open(target / "concepts.csv")))
    assert concept_rows, "no concepts materialized"
    assert all(r["canonical_urn"] == CANON for r in concept_rows)
    assert any(r["concept_id"] == "widget" for r in concept_rows)

    # ── every emitted EDGE row keys on the canonical_urn ──
    edge_rows = list(csv.DictReader(open(target / "semantic_edges.csv")))
    assert edge_rows and all(r["canonical_urn"] == CANON for r in edge_rows)

    # ── fingerprints are re-keyed by canonical_urn ──
    fps = json.loads((target / "fingerprints.json").read_text())
    assert set(fps) == {CANON}
    assert fps[CANON]["canonical_urn"] == CANON


def test_materialize_does_not_touch_the_versum_store(tmp_path):
    folder = tmp_path / "corpus"
    folder.mkdir()
    _build_indexed_folder(folder)
    v = folder / ".versum"
    _curate_a_concept(v)

    before = _store_bytes(v)
    materialize(folder, tmp_path / "kg-layer", library="dls-knowledge")
    after = _store_bytes(v)
    # the KG provenance linkage / store is byte-for-byte untouched (additive, referencing)
    assert before == after
    # materialize writes a FLAT KG-canonical layer, not a shadow .versum store
    assert not (tmp_path / "kg-layer" / ".versum").exists()


def test_materialize_is_idempotent_second_call_is_noop(tmp_path):
    folder = tmp_path / "corpus"
    folder.mkdir()
    _build_indexed_folder(folder)
    _curate_a_concept(folder / ".versum")

    target = tmp_path / "kg-layer"
    first = materialize(folder, target)
    snap1 = _target_bytes(target)
    assert first["n_files_written"] > 0 and first["no_op"] is False

    second = materialize(folder, target)
    snap2 = _target_bytes(target)
    # identical bytes on the unchanged folder — a true no-op
    assert snap1 == snap2
    assert second["no_op"] is True
    assert second["n_files_written"] == 0


def test_materialize_refuses_to_write_the_source_store(tmp_path):
    folder = tmp_path / "corpus"
    folder.mkdir()
    _build_indexed_folder(folder)
    with pytest.raises(ValueError):
        materialize(folder, folder / ".versum")
