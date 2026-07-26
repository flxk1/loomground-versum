"""The drop-in feature: index ANY folder of files, domain-agnostically.

Uses the ``generic`` profile on plain-text files (no PDF, no law) so it proves the
folder indexer works for arbitrary knowledge, not just the legal corpus.
"""
import json
from pathlib import Path

import pytest

from versum.store.index import index_folder
from versum.store import graph as g
from versum.profile import get_profile
import versum.profiles  # noqa: F401 — register built-ins


def _make_corpus(root: Path):
    (root / "notes").mkdir(parents=True, exist_ok=True)
    (root / "a.md").write_text(
        "# Photosynthesis\n\nChlorophyll is defined as the green pigment. "
        "Sunlight causes the reaction that every leaf performs.\n", encoding="utf-8")
    (root / "notes" / "b.txt").write_text(
        "Entropy is defined as disorder. Friction causes heat in any system.\n",
        encoding="utf-8")
    (root / "image.bin").write_bytes(b"\x00\x01not text")  # unsupported -> skipped


def test_index_any_folder(tmp_path):
    _make_corpus(tmp_path)
    manifest = index_folder(tmp_path, profile_id="generic")

    v = tmp_path / ".versum"
    for name in ("claims.csv", "sources.csv", "fingerprints.json",
                 "concepts.csv", "semantic_edges.csv", "index.json"):
        assert (v / name).exists(), f"missing {name}"

    assert manifest["n_sources"] == 2          # a.md + notes/b.txt
    assert manifest["n_claims"] > 0            # markers fired
    assert manifest["profile"] == "generic"
    assert manifest["namespace"] == "kg"
    assert any("image.bin" in s for s in manifest["skipped"])  # recorded, not dropped


def test_indexed_claims_valid_under_profile(tmp_path):
    _make_corpus(tmp_path)
    index_folder(tmp_path, profile_id="generic")
    profile = get_profile("generic")
    claims = g.load_claims(tmp_path / ".versum" / "claims.csv")
    assert claims
    for c in claims:
        assert profile.is_valid("predicate", c["predicate"])
        assert profile.is_valid("modality", c["modality"])
        assert profile.is_valid("quantification", c["quantification"])
        assert c["source_urn"].startswith("urn:kg:sha256:")  # on-disk file -> content rung


def test_fingerprints_fixed_shape(tmp_path):
    _make_corpus(tmp_path)
    index_folder(tmp_path, profile_id="generic")
    fps = json.loads((tmp_path / ".versum" / "fingerprints.json").read_text())
    profile = get_profile("generic")
    for urn, fpr in fps.items():
        # dim5 histogram keys are the profile's closed sets — fixed shape per profile
        assert set(fpr["dim5"]["predicate"]) == set(profile.predicates)
        assert set(fpr["dim5"]["modality"]) == set(profile.modalities)


def test_reindex_preserves_curation(tmp_path):
    _make_corpus(tmp_path)
    index_folder(tmp_path, profile_id="generic")
    # simulate a curator writing a concept + a hand edge
    v = tmp_path / ".versum"
    g.save_concepts(v / "concepts.csv",
                    [g.Concept("energy-transfer", "Energy transfer", "science")])
    claims = g.load_claims(v / "claims.csv")
    first = claims[0]["item_id"]
    g.save_edges(v / "semantic_edges.csv",
                 [g.Edge("e1", first, "energy-transfer", "grounds")])
    # re-index: claims regenerate, but curation output survives
    index_folder(tmp_path, profile_id="generic")
    concepts = g.load_concepts(v / "concepts.csv")
    edges = g.load_edges(v / "semantic_edges.csv")
    assert any(c["concept_id"] == "energy-transfer" for c in concepts)
    assert any(e["dst_id"] == "energy-transfer" for e in edges)
