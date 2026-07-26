"""The KG-provenance join — proven through the pipeline, not hardcoded.

A folder that already carries a KG capture sidecar (`canonical_urn`) must have its claims
keyed on that same URN (reused, not minted), its citation stub skipped, and the both-ways
traversal resolve on the canonical URN — end to end. Unlike the retired hand-rigged demo,
the URN is NEVER passed into extract(); it is read from the sidecar by the pipeline.
"""
import csv
from pathlib import Path

from versum.store.index import index_folder
from versum.concept import curate
from versum.store import graph as g
import versum.profiles  # noqa: F401


def _kg_folder(root: Path) -> str:
    urn = "urn:dls:celex:32099zz9999"
    # a KG citation stub + its capture sidecar (as capture-to-kg / deep-research write them)
    (root / "2099-x.md").write_text("# Stub\ncitation only\n", encoding="utf-8")
    (root / "2099-x.md.metadata.json").write_text(
        '{"canonical_urn": "%s", "title": "X", "pdf_status": "available"}' % urn,
        encoding="utf-8")
    # the source file that "arrived out-of-band" — filename shares the CELEX id token
    (root / "CELEX_32099ZZ9999.md").write_text(
        "'Controller' is defined as the body which determines the purposes. "
        "The controller shall ensure protection in every case.\n", encoding="utf-8")
    return urn


def test_kg_provenance_reused_not_minted(tmp_path):
    urn = _kg_folder(tmp_path)
    m = index_folder(tmp_path, "law-eu")
    assert m["n_kg_reused"] == 1
    assert any("kg stub" in s for s in m["skipped"])          # stub skipped as a source
    claims = g.load_claims(tmp_path / ".versum" / "claims.csv")
    assert claims
    # every claim carries the KG's canonical_urn — reused, never a minted urn
    assert all(c["source_urn"] == urn for c in claims), \
        f"claims not keyed on the KG urn: {[c['source_urn'] for c in claims][:3]}"
    srcs = list(csv.DictReader(open(tmp_path / ".versum" / "sources.csv")))
    assert all(s["provenance"] == "kg-canonical" for s in srcs)


def test_both_ways_joins_on_canonical_urn_through_pipeline(tmp_path):
    urn = _kg_folder(tmp_path)
    index_folder(tmp_path, "law-eu")
    curate.suggest_folder(tmp_path)
    curate.confirm_folder(tmp_path, min_sources=1)
    claims = g.load_claims(tmp_path / ".versum" / "claims.csv")
    edges = g.load_edges(tmp_path / ".versum" / "semantic_edges.csv")
    # the URN was NEVER passed to extract(); it came from the sidecar via kg.provenance_urn_for
    models = g.models_for_source(urn, claims, edges)
    assert len(models) > 0, f"pipeline join failed: models_for_source({urn}) is empty"


def test_no_sidecar_falls_back_to_minted(tmp_path):
    # a plain folder with no KG sidecar still works, minting its own urn
    (tmp_path / "note.md").write_text(
        "'Widget' is defined as a thing. A widget causes value.\n", encoding="utf-8")
    m = index_folder(tmp_path, "generic")
    assert m["n_kg_reused"] == 0
    srcs = list(csv.DictReader(open(tmp_path / ".versum" / "sources.csv")))
    assert srcs and all(s["provenance"] == "minted" for s in srcs)
    assert all(s["source_urn"].startswith("urn:kg:sha256:") for s in srcs)  # content rung
