"""Domain-openness: fingerprint + invariants work with zero law vocabulary."""
from versum.store import graph
from versum.identity.fingerprint import fingerprint
from versum.profiles.generic import PROFILE as GENERIC

URN = "urn:kg:source:demo"


def _claims():
    return [
        {"item_id": "item-1", "source_urn": URN, "predicate": "defines",
         "modality": "definitional", "quantification": "null"},
        {"item_id": "item-2", "source_urn": URN, "predicate": "causes",
         "modality": "asserted", "quantification": "universal"},
        {"item_id": "item-3", "source_urn": URN, "predicate": "causes",
         "modality": "asserted", "quantification": "existential"},
    ]


def test_generic_fingerprint_fixed_shape():
    fp = fingerprint(URN, _claims(), GENERIC)
    assert fp["n_claims"] == 3
    # histogram keys are exactly the profile's closed sets (fixed shape)
    assert set(fp["dim5"]["predicate"]) == set(GENERIC.predicates)
    assert set(fp["dim5"]["modality"]) == set(GENERIC.modalities)
    assert set(fp["dim5"]["quantification"]) == set(GENERIC.quantifications)
    assert fp["dim5"]["predicate"]["causes"] == 2
    assert fp["dim5"]["predicate"]["defines"] == 1
    assert fp["nd"]["namespace"] == "kg"


def test_generic_invariants():
    claims = _claims()
    concepts = [{"concept_id": "gravity", "label": "Gravity", "domain": "physics",
                 "definition": "", "catalogue_version": "generic-v0", "created_by": "t"}]
    edges = [{"edge_id": "e1", "src_id": "item-1", "dst_id": "gravity",
              "edge_type": "grounds", "rationale": "", "confidence": "",
              "verification": "candidate"}]

    assert graph.check_no_orphan_claims(claims, {URN}) == []
    assert graph.check_no_orphan_edges(claims, concepts, edges) == []
    assert graph.check_concept_ids_own_identity(concepts) == []

    # domain-openness: the generic profile carries no legal vocabulary
    assert GENERIC.principles == frozenset()
    assert "obliged" not in GENERIC.modalities
    assert graph.models_for_source(URN, claims, edges) == {"gravity"}
    assert graph.sources_for_model("gravity", claims, edges) == {URN}
