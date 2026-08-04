"""The asymmetric folder hierarchy + publish/distribution model.

Memory flows UP (a folder sees its own + every descendant store) and NOT sideways or down,
except that an ancestor's explicitly *published* items flow DOWN. Publication is recorded on
the append-only event log (never rewritten); erasure always wins, so a tombstoned item is
never distributed. ``from_folder(...).search_similar`` runs over the whole aggregated scope.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from versum.events import read_events
from versum.store import distribution, erasure
from versum.store.hierarchy import (
    aggregate_docs,
    discover_ancestors,
    discover_descendants,
    from_folder,
    kg_root_for,
)

CLAIM_COLUMNS = ["canonical_urn", "library", "item_id", "text", "polarity", "predicate",
                 "modality", "quantification", "dimension"]


def _store(folder: Path, claims: list[dict], *, domain: str = "privacy") -> Path:
    """Materialise a ``.versum`` store under ``folder`` with the given claim rows."""
    kg = kg_root_for(folder)
    bd = kg / "by-domain" / domain
    bd.mkdir(parents=True, exist_ok=True)
    with open(bd / "claims.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CLAIM_COLUMNS)
        w.writeheader()
        for c in claims:
            w.writerow({k: c.get(k, "") for k in CLAIM_COLUMNS})
    urns = sorted({c["canonical_urn"] for c in claims})
    with open(bd / "sources.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["source_urn", "canonical_urn", "path"])
        w.writeheader()
        for u in urns:
            w.writerow({"source_urn": u, "canonical_urn": u, "path": f"{u}.txt"})
    (bd / "fingerprints.json").write_text(
        json.dumps({u: {"canonical_urn": u} for u in urns}), encoding="utf-8")
    return kg


def _claim(item_id, urn, text):
    return {"canonical_urn": urn, "library": "L", "item_id": item_id, "text": text,
            "polarity": "D", "predicate": "imposes", "modality": "obliged",
            "quantification": "null", "dimension": "deontic"}


def _workspace(tmp_path: Path):
    """workspace/  (root) → eng/  → eng/platform/, each a ``.versum`` store."""
    ws = tmp_path / "workspace"
    eng = ws / "eng"
    plat = eng / "platform"
    for d in (ws, eng, plat):
        d.mkdir(parents=True, exist_ok=True)
    _store(ws, [_claim("w1", "urn:w", "the parent policy governs all subsidiary data"),
                _claim("w2", "urn:w", "the parent policy names a data protection officer")])
    _store(eng, [_claim("e1", "urn:e", "the engineering team must log every deployment")])
    _store(plat, [_claim("p1", "urn:p", "the platform service caches user sessions")])
    return ws, eng, plat


def _ids(folder):
    return {d.doc_id for d in aggregate_docs(folder)}


# ── 1. ancestry discovery ────────────────────────────────────────
def test_ancestry_discovery(tmp_path):
    ws, eng, plat = _workspace(tmp_path)

    assert discover_descendants(eng) == sorted([eng.resolve(), plat.resolve()])
    assert discover_descendants(ws) == sorted([ws.resolve(), eng.resolve(), plat.resolve()])

    assert discover_ancestors(eng) == [ws.resolve()]              # strict, shallowest-first
    assert discover_ancestors(plat) == [ws.resolve(), eng.resolve()]
    assert discover_ancestors(ws) == []                           # root has no ancestor
    assert discover_descendants(plat) == [plat.resolve()]         # leaf sees only itself


# ── 2. own + descendant aggregation (memory flows UP) ────────────
def test_own_and_descendant_aggregation(tmp_path):
    ws, eng, plat = _workspace(tmp_path)

    # eng sees its own claim + its descendant's, but NOT its parent's private claims.
    assert _ids(eng) == {"claim:e1", "claim:p1"}
    # the root sees everything beneath it.
    assert _ids(ws) == {"claim:w1", "claim:w2", "claim:e1", "claim:p1"}
    # a leaf sees only itself (nothing flows down yet).
    assert _ids(plat) == {"claim:p1"}


# ── 3. a non-published ancestor item is NOT visible down ──────────
def test_unpublished_ancestor_item_is_invisible_down(tmp_path):
    ws, eng, plat = _workspace(tmp_path)
    # No publish anywhere → the parent's claims never reach eng or platform.
    assert "claim:w1" not in _ids(eng)
    assert "claim:w1" not in _ids(plat)
    assert "claim:e1" not in _ids(plat)          # sibling-of-ancestor stays out of scope too


# ── 4. a published ancestor item flows DOWN to every descendant ──
def test_published_item_visible_to_descendants(tmp_path):
    ws, eng, plat = _workspace(tmp_path)

    result = distribution.publish(kg_root_for(ws), "claim:w1", actor="lead")
    assert result["grade"] == "published" and result["scope"] == "descendants"

    assert "claim:w1" in _ids(eng)               # one level down
    assert "claim:w1" in _ids(plat)              # two levels down
    assert "claim:w2" not in _ids(eng)           # the un-published sibling stays private


def test_publish_source_distributes_every_claim(tmp_path):
    ws, eng, plat = _workspace(tmp_path)

    result = distribution.publish(kg_root_for(ws), "urn:w", actor="lead")  # a source urn
    assert result["grade"] == "published"
    assert set(result["affected_claim_ids"]) == {"w1", "w2"}

    assert {"claim:w1", "claim:w2"} <= _ids(eng)   # every claim of the source flows down
    assert {"claim:w1", "claim:w2"} <= _ids(plat)


# ── 5. unpublish reverts ─────────────────────────────────────────
def test_unpublish_reverts(tmp_path):
    ws, eng, plat = _workspace(tmp_path)
    distribution.publish(kg_root_for(ws), "claim:w1")
    assert "claim:w1" in _ids(eng)

    distribution.unpublish(kg_root_for(ws), "claim:w1")
    assert "claim:w1" not in _ids(eng)           # stops flowing down
    assert "claim:w1" not in _ids(plat)


def test_unpublish_source_reverts(tmp_path):
    ws, eng, _ = _workspace(tmp_path)
    distribution.publish(kg_root_for(ws), "urn:w")
    assert {"claim:w1", "claim:w2"} <= _ids(eng)

    distribution.unpublish(kg_root_for(ws), "urn:w")
    assert "claim:w1" not in _ids(eng) and "claim:w2" not in _ids(eng)


# ── 6. erasure always wins: erased items are never distributed ────
def test_erased_ancestor_item_is_never_distributed(tmp_path):
    ws, eng, plat = _workspace(tmp_path)
    distribution.publish(kg_root_for(ws), "claim:w1")
    assert "claim:w1" in _ids(eng)               # published and visible…

    erasure.delete(kg_root_for(ws), "claim:w1")  # …then tombstoned in the ancestor
    assert "claim:w1" not in _ids(eng)           # erasure wins over an active publish
    assert "claim:w1" not in _ids(plat)


def test_purged_published_source_is_never_distributed(tmp_path):
    ws, eng, _ = _workspace(tmp_path)
    distribution.publish(kg_root_for(ws), "urn:w")
    assert {"claim:w1", "claim:w2"} <= _ids(eng)

    erasure.purge_by_source(kg_root_for(ws), "urn:w", reason="art.17")
    assert "claim:w1" not in _ids(eng) and "claim:w2" not in _ids(eng)


# ── search_similar runs over the aggregated scope ────────────────
def test_search_similar_over_aggregated_scope(tmp_path):
    ws, eng, plat = _workspace(tmp_path)

    # descendant content is reachable from eng's search…
    hits = from_folder(eng).search_similar("platform caches user sessions", k=5)
    assert hits and hits[0]["doc_id"] == "claim:p1"

    # …ancestor content is NOT, until it is published.
    assert from_folder(eng).search_similar("parent policy subsidiary data", k=5) == []
    distribution.publish(kg_root_for(ws), "claim:w1")
    hits = from_folder(eng).search_similar("parent policy subsidiary data", k=5)
    assert hits and hits[0]["doc_id"] == "claim:w1"


# ── distribution is a signed, replayable projection ──────────────
def test_distribution_recorded_as_signed_events(tmp_path):
    ws, _, _ = _workspace(tmp_path)
    kg = kg_root_for(ws)
    distribution.publish(kg, "claim:w1", reason="r1")
    distribution.unpublish(kg, "claim:w1")
    distribution.publish(kg, "urn:w")

    events = read_events(kg)                      # validates contiguity + the digest chain
    kinds = [e["event_type"] for e in events]
    assert kinds == [distribution.PUBLISH_EVENT, distribution.UNPUBLISH_EVENT,
                     distribution.SOURCE_PUBLISH_EVENT]
    assert all(e["event_id"].startswith("event:") for e in events)


def test_distribution_projection_rebuilds_from_the_log(tmp_path):
    ws, _, _ = _workspace(tmp_path)
    kg = kg_root_for(ws)
    distribution.publish(kg, "claim:w1")
    distribution.publish(kg, "urn:w")
    before = distribution.load_distribution(kg)

    (Path(kg) / distribution.DISTRIBUTION_FILE).unlink()          # drop the projection
    distribution.rebuild_distribution_projection(kg)             # refold from the events
    after = distribution.load_distribution(kg)
    assert after.published_nodes == before.published_nodes
    assert after.published_sources == before.published_sources
