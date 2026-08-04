"""Logical delete + GDPR Art.17 purge: erased nodes vanish from every read and from
search, purge removes content but leaves a signed tombstone, delete_by_source scopes to
one source, and untouched nodes are unaffected. History is never rewritten — every
erasure is a fresh, chained event on the append-only log."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from versum.events import read_events
from versum.store import erasure
from versum.store.retrieve import docs_from_kg, from_kg

CLAIM_COLUMNS = ["canonical_urn", "library", "item_id", "text", "polarity", "predicate",
                 "modality", "quantification", "dimension"]


def _build_store(tmp_path: Path) -> Path:
    """A minimal by-domain store: two sources, three claims, one concept."""
    bd = tmp_path / "by-domain" / "privacy"
    bd.mkdir(parents=True)
    rows = [
        {"canonical_urn": "urn:a", "library": "L", "item_id": "c1",
         "text": "the controller must ensure protection of personal data",
         "polarity": "D", "predicate": "imposes", "modality": "obliged",
         "quantification": "null", "dimension": "deontic"},
        {"canonical_urn": "urn:a", "library": "L", "item_id": "c2",
         "text": "the controller shall document every processing purpose",
         "polarity": "D", "predicate": "imposes", "modality": "obliged",
         "quantification": "null", "dimension": "deontic"},
        {"canonical_urn": "urn:b", "library": "L", "item_id": "c3",
         "text": "the processor may transfer data abroad with consent",
         "polarity": "P", "predicate": "permits", "modality": "permitted",
         "quantification": "null", "dimension": "deontic"},
    ]
    with open(bd / "claims.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CLAIM_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    with open(bd / "sources.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["source_urn", "canonical_urn", "path"])
        w.writeheader()
        w.writerow({"source_urn": "urn:a", "canonical_urn": "urn:a", "path": "a.txt"})
        w.writerow({"source_urn": "urn:b", "canonical_urn": "urn:b", "path": "b.txt"})
    (bd / "fingerprints.json").write_text(
        json.dumps({"urn:a": {"canonical_urn": "urn:a"},
                    "urn:b": {"canonical_urn": "urn:b"}}), encoding="utf-8")
    (tmp_path / "canon.json").write_text(json.dumps({"concepts": [
        {"concept_id": "controller", "label": "controller", "predicate": "imposes",
         "domains": ["privacy"], "m": 1},
        {"concept_id": "processor", "label": "processor", "predicate": "permits",
         "domains": ["privacy"], "m": 1}]}), encoding="utf-8")
    return tmp_path


def _ids(kg_root):
    return {d.doc_id for d in docs_from_kg(kg_root)}


def _claim_texts(kg_root):
    path = Path(kg_root) / "by-domain" / "privacy" / "claims.csv"
    with open(path, newline="", encoding="utf-8") as fh:
        return [r["text"] for r in csv.DictReader(fh)]


# ── logical delete ───────────────────────────────────────────────
def test_deleted_claim_disappears_from_reads_and_search(tmp_path):
    root = _build_store(tmp_path)
    assert "claim:c1" in _ids(root)

    erasure.delete(root, "claim:c1", reason="art.17 request", actor="dpo")

    assert "claim:c1" not in _ids(root)                       # gone from the read projection
    hits = from_kg(root).search("controller protection data", k=10)
    assert all(h["doc_id"] != "claim:c1" for h in hits)       # gone from BM25 search
    sim = from_kg(root).search_similar("controller protection data", k=10)
    assert all(h["doc_id"] != "claim:c1" for h in sim)        # gone from keyword-overlap search


def test_deleted_concept_disappears_from_search(tmp_path):
    root = _build_store(tmp_path)
    erasure.delete(root, "concept:processor")
    assert "concept:processor" not in _ids(root)
    assert "concept:controller" in _ids(root)


def test_logical_delete_keeps_content_and_is_recoverable(tmp_path):
    root = _build_store(tmp_path)
    erasure.delete(root, "claim:c1")

    assert any("protection of personal data" in t for t in _claim_texts(root))  # content stays
    tombs = erasure.load_tombstones(root)
    assert "claim:c1" in tombs.deleted_nodes and "claim:c1" not in tombs.purged_nodes

    erasure.restore(root, "claim:c1")
    assert "claim:c1" in _ids(root)                            # recovered into reads


def test_delete_only_hides_the_target(tmp_path):
    root = _build_store(tmp_path)
    before = _ids(root)
    erasure.delete(root, "claim:c1")
    assert _ids(root) == before - {"claim:c1"}                 # nothing else moved


# ── delete_by_source scoping ─────────────────────────────────────
def test_delete_by_source_scopes_to_one_document(tmp_path):
    root = _build_store(tmp_path)
    report = erasure.delete_by_source(root, "urn:a")
    assert set(report["affected_claim_ids"]) == {"c1", "c2"}

    ids = _ids(root)
    assert "claim:c1" not in ids and "claim:c2" not in ids     # both nodes of urn:a hidden
    assert "claim:c3" in ids                                   # the other source untouched
    assert erasure.restore_source(root, "urn:a")
    assert {"claim:c1", "claim:c2"} <= _ids(root)              # recoverable


# ── purge (GDPR Art.17 hard erasure) ─────────────────────────────
def test_purge_removes_content_but_leaves_tombstone(tmp_path):
    root = _build_store(tmp_path)
    result = erasure.purge(root, "claim:c1", reason="art.17", actor="dpo")

    texts = _claim_texts(root)
    assert not any("protection of personal data" in t for t in texts)   # content removed
    assert any("document every processing purpose" in t for t in texts)  # sibling kept

    tombs = erasure.load_tombstones(root)
    assert "claim:c1" in tombs.purged_nodes                    # tombstone marker remains
    assert result["content_digest"].startswith("sha256:")
    assert "claim:c1" not in _ids(root)                        # excluded from reads


def test_purged_node_cannot_be_restored(tmp_path):
    root = _build_store(tmp_path)
    erasure.purge(root, "claim:c1")
    with pytest.raises(ValueError, match="purged"):
        erasure.restore(root, "claim:c1")


def test_purge_by_source_removes_all_content_and_leaves_tombstone(tmp_path):
    root = _build_store(tmp_path)
    result = erasure.purge_by_source(root, "urn:a", reason="art.17")
    assert set(result["affected_claim_ids"]) == {"c1", "c2"}

    texts = _claim_texts(root)
    assert texts == ["the processor may transfer data abroad with consent"]  # only urn:b left

    src_path = Path(root) / "by-domain" / "privacy" / "sources.csv"
    with open(src_path, newline="", encoding="utf-8") as fh:
        assert [r["canonical_urn"] for r in csv.DictReader(fh)] == ["urn:b"]
    fps = json.loads((Path(root) / "by-domain" / "privacy" / "fingerprints.json").read_text())
    assert "urn:a" not in fps and "urn:b" in fps               # fingerprint erased too

    tombs = erasure.load_tombstones(root)
    assert "urn:a" in tombs.purged_sources
    assert _ids(root) == {"claim:c3", "concept:controller", "concept:processor"}


# ── history is appended, never rewritten ─────────────────────────
def test_erasure_is_recorded_as_signed_events(tmp_path):
    root = _build_store(tmp_path)
    erasure.delete(root, "claim:c1", reason="r1")
    erasure.purge(root, "claim:c2", reason="r2")
    erasure.delete_by_source(root, "urn:b")

    events = read_events(root)          # validates contiguity + the digest chain
    kinds = [e["event_type"] for e in events]
    assert kinds == [erasure.DELETE_EVENT, erasure.PURGE_EVENT, erasure.SOURCE_DELETE_EVENT]
    assert all(e["event_id"].startswith("event:") for e in events)
    assert events[1]["payload"]["content_digest"].startswith("sha256:")


def test_bad_node_id_is_rejected(tmp_path):
    root = _build_store(tmp_path)
    for bad in ("c1", "widget:1", "claim:"):
        with pytest.raises(ValueError):
            erasure.delete(root, bad)


def test_erasure_projection_rebuilds_from_the_log(tmp_path):
    root = _build_store(tmp_path)
    erasure.delete(root, "claim:c1")
    erasure.purge(root, "claim:c3")
    before = erasure.load_tombstones(root)

    (Path(root) / erasure.ERASURE_FILE).unlink()               # drop the projection
    erasure.rebuild_erasure_projection(root)                   # refold it from the events
    after = erasure.load_tombstones(root)
    assert after.deleted_nodes == before.deleted_nodes
    assert after.purged_nodes == before.purged_nodes
