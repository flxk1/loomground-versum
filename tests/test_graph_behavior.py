"""More graph coverage — CSV round-trip, invariants, and grounding traversals.

Domain-neutral fixtures (namespace ``kg``); no profile vocabulary needed.
"""
from versum.store import graph as g
# ── CSV round-trip ───────────────────────────────────────────────
def test_round_trip_concepts_claims_edges(tmp_path):
    # concepts
    cpath = tmp_path / "concepts.csv"
    g.save_concepts(cpath, [g.Concept("gravity", "Gravity", "physics",
                                      "the attractive force", "generic-v0", "tester")])
    concepts = g.load_concepts(cpath)
    assert concepts[0]["concept_id"] == "gravity"
    assert concepts[0]["label"] == "Gravity"
    assert concepts[0]["definition"] == "the attractive force"

    # claims — span list flattens to span_start/span_end and loads back as int
    clpath = tmp_path / "claims.csv"
    claim = {"item_id": "item-1", "source_urn": "urn:kg:source:a",
             "span": [10, 42], "predicate": "causes", "modality": "asserted",
             "quantification": "null", "text": "X causes Y."}
    g.save_claims(clpath, [claim], "generic")
    loaded = g.load_claims(clpath)
    assert loaded[0]["item_id"] == "item-1"
    assert loaded[0]["span_start"] == 10 and isinstance(loaded[0]["span_start"], int)
    assert loaded[0]["span_end"] == 42 and isinstance(loaded[0]["span_end"], int)
    assert loaded[0]["profile"] == "generic"

    # edges
    epath = tmp_path / "edges.csv"
    g.save_edges(epath, [g.Edge("e1", "item-1", "gravity", "grounds", "why", "0.9",
                                "confirmed")])
    edges = g.load_edges(epath)
    assert edges[0]["edge_id"] == "e1"
    assert edges[0]["dst_id"] == "gravity"
    assert edges[0]["edge_type"] == "grounds"
    assert edges[0]["verification"] == "confirmed"


# ── invariants ───────────────────────────────────────────────────
def test_check_no_orphan_claims_flags_unknown_source():
    claims = [{"item_id": "item-1", "source_urn": "urn:kg:source:ghost"}]
    violations = g.check_no_orphan_claims(claims, {"urn:kg:source:real"})
    assert len(violations) == 1
    assert "item-1" in violations[0]
    # and passes when the urn is known
    assert g.check_no_orphan_claims(claims, {"urn:kg:source:ghost"}) == []


def test_check_no_orphan_edges_flags_grounds_and_non_grounds():
    claims = [{"item_id": "item-1", "source_urn": "urn:kg:source:a"}]
    concepts = [{"concept_id": "known"}]
    edges = [
        # grounds edge to a concept that doesn't exist
        {"edge_id": "e1", "src_id": "item-1", "dst_id": "missing-concept",
         "edge_type": "grounds"},
        # non-grounds edge whose endpoint isn't a known concept
        {"edge_id": "e2", "src_id": "known", "dst_id": "ghost-concept",
         "edge_type": "rhymes_with"},
    ]
    violations = g.check_no_orphan_edges(claims, concepts, edges)
    joined = " ".join(violations)
    assert "e1" in joined and "missing-concept" in joined
    assert "e2" in joined and "ghost-concept" in joined


def test_check_no_orphan_edges_clean_when_endpoints_known():
    claims = [{"item_id": "item-1", "source_urn": "urn:kg:source:a"}]
    concepts = [{"concept_id": "a"}, {"concept_id": "b"}]
    edges = [
        {"edge_id": "e1", "src_id": "item-1", "dst_id": "a", "edge_type": "grounds"},
        {"edge_id": "e2", "src_id": "a", "dst_id": "b", "edge_type": "rhymes_with"},
    ]
    assert g.check_no_orphan_edges(claims, concepts, edges) == []


def test_check_concept_ids_own_identity_flags_urn_and_source_urn():
    known = {"urn:kg:source:a"}
    concepts = [
        {"concept_id": "urn:kg:source:x"},  # urn-shaped id
        {"concept_id": "urn:kg:source:a"},  # equals a known source urn
        {"concept_id": "good-slug"},         # fine
    ]
    violations = g.check_concept_ids_own_identity(concepts, known)
    joined = " ".join(violations)
    assert "is a urn" in joined
    assert "equals a known source urn" in joined
    assert "good-slug" not in joined


# ── traversals ignore non-grounds edges ──────────────────────────
def test_traversals_ignore_non_grounds_edges():
    claims = [{"item_id": "i1", "source_urn": "urn:kg:source:s"}]
    edges = [
        {"edge_id": "e1", "src_id": "i1", "dst_id": "concept-c", "edge_type": "grounds"},
        {"edge_id": "e2", "src_id": "i1", "dst_id": "concept-d",
         "edge_type": "rhymes_with"},  # must not leak into grounding
    ]
    assert g.models_for_source("urn:kg:source:s", claims, edges) == {"concept-c"}
    assert g.sources_for_model("concept-c", claims, edges) == {"urn:kg:source:s"}
    # the rhymes_with target is not reachable by grounding traversal
    assert g.sources_for_model("concept-d", claims, edges) == set()
