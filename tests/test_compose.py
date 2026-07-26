"""M>1 coordinate composition (task #55): coordinate pairs co-occurring within a unit and
recurring across sources become depth-2 composite concepts; bounded and off at m_max=1.
"""
from versum.concept import canon
def _c(iid, urn, unit, text, predicate):
    return {"item_id": iid, "canonical_urn": urn, "source_urn": urn, "unit_id": unit,
            "text": text, "polarity": "D", "predicate": predicate, "modality": "obliged",
            "quantification": "null", "domain": "d", "library": "L", "marker": "x"}


def _pair_corpus():
    # two coordinates ('controller' obligation, 'processor' obligation) co-occur in the SAME
    # unit across two sources → a recurring pair.
    return [
        _c("a1", "urn:x:1", "Article-1", "A 'controller' has a duty.", "imposes"),
        _c("a2", "urn:x:1", "Article-1", "A 'processor' has a duty.", "imposes"),
        _c("b1", "urn:x:2", "Article-1", "The 'controller' has a duty.", "imposes"),
        _c("b2", "urn:x:2", "Article-1", "The 'processor' has a duty.", "imposes"),
    ]


def test_m1_mints_no_composites():
    out = canon.build_canon(_pair_corpus(), m_max=1, min_df=1)
    assert out.get("n_composite", 0) == 0
    assert not any(k.startswith("m2-") for k in out["concepts"])


def test_m2_mints_recurring_pair():
    out = canon.build_canon(_pair_corpus(), m_max=2, min_df=1, min_support_m=2)
    comps = [k for k in out["concepts"] if k.startswith("m2-")]
    assert len(comps) == 1 and out["n_composite"] == 1
    agg = out["concepts"][comps[0]]
    assert agg["coord"]["m"] == 2 and len(agg["coord"]["constituents"]) == 2
    assert len(agg["sources"]) == 2                      # recurred across both sources
    # composite is grounded (canonical-keyed grounds edges exist) and in the fingerprints
    assert any(e["dst_id"] == comps[0] for e in out["edges"])
    assert comps[0] in out["fingerprints"]["urn:x:1"]
    roles = {e["semantic_role"] for e in out["composition_edges"]
             if e["dst_id"] == comps[0]}
    assert roles == {"member:1", "member:2"}
    assert all(e["dimension"] == "structural" for e in out["composition_edges"])


def test_composite_id_is_deterministic_and_valid():
    from versum.store.graph import CONCEPT_ID_RE
    a = canon.build_canon(_pair_corpus(), m_max=2, min_df=1)
    b = canon.build_canon(_pair_corpus(), m_max=2, min_df=1)
    ca = sorted(k for k in a["concepts"] if k.startswith("m2-"))
    cb = sorted(k for k in b["concepts"] if k.startswith("m2-"))
    assert ca == cb and all(CONCEPT_ID_RE.match(k) for k in ca)


def test_min_support_bounds_composites():
    # a pair that co-occurs in only ONE source is dropped at min_support=2
    corpus = [
        _c("a1", "urn:x:1", "Article-1", "A 'controller' has a duty.", "imposes"),
        _c("a2", "urn:x:1", "Article-1", "A 'processor' has a duty.", "imposes"),
    ]
    out = canon.build_canon(corpus, m_max=2, min_df=1, min_support_m=2)
    assert out["n_composite"] == 0


def test_no_unit_no_composition():
    # claims without unit_id cannot establish co-occurrence
    corpus = [
        {**_c("a1", "urn:x:1", "", "A 'controller' has a duty.", "imposes")},
        {**_c("a2", "urn:x:1", "", "A 'processor' has a duty.", "imposes")},
        {**_c("b1", "urn:x:2", "", "The 'controller' has a duty.", "imposes")},
        {**_c("b2", "urn:x:2", "", "The 'processor' has a duty.", "imposes")},
    ]
    out = canon.build_canon(corpus, m_max=2, min_df=1, min_support_m=2)
    assert out["n_composite"] == 0
