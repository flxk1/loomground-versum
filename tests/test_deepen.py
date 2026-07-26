"""LLM deepening harness (ADR-005): deterministic bounded selection; additive, model-free core."""
from versum import deepen
from versum.concept import canon


def _c(iid, urn, unit, text, predicate="asserts"):
    return {"item_id": iid, "canonical_urn": urn, "source_urn": urn, "unit_id": unit,
            "text": text, "polarity": "D", "predicate": predicate, "modality": "asserted",
            "quantification": "null", "domain": "d", "library": "L", "marker": "x"}


def test_null_deepener_is_default_no_records():
    claims = [_c("i1", "u:1", "U1", "A 'thing' is described.")]
    assert deepen.deepen(claims) == []           # NullDeepener → nothing


def test_budget_bounds_calls():
    claims = [_c(f"i{n}", "u:1", "U1", f"Claim number {n} here.") for n in range(10)]
    recs = deepen.deepen(claims, deepener=deepen.EchoDeepener(), budget=3)
    assert len(recs) <= 3


def test_residue_first_selects_unclustered():
    # build a canon where only 'controller' clusters (quoted, recurs); a bare claim is residue
    clustered = [
        _c("a1", "u:1", "U1", "A 'controller' has a duty."),
        _c("a2", "u:2", "U1", "The 'controller' has a duty."),
    ]
    residue = _c("r1", "u:3", "U9", "Some unclusterable narrative sentence without a subject.")
    claims = clustered + [residue]
    cn = canon.build_canon(claims, min_df=2)
    cands = deepen.escalation_candidates(claims, canon=cn, budget=1, policy="residue-first")
    assert cands and cands[0]["item_id"] == "r1"     # residue picked first


def test_deepen_is_additive_and_deterministic(tmp_path):
    claims = [_c("i1", "u:1", "U1", "First part; second part."),
              _c("i2", "u:1", "U1", "Alpha; beta; gamma.")]
    out = tmp_path / "deepenings.jsonl"
    a = deepen.deepen(claims, deepener=deepen.EchoDeepener(), budget=10, out_path=out)
    b = deepen.deepen(claims, deepener=deepen.EchoDeepener(), budget=10)
    assert a == b and a                          # deterministic given a deterministic adapter
    assert out.exists() and out.read_text().count("\n") == len(a)
    # records carry provenance and validated shape
    assert all(set(("canonical_urn", "item_id", "deepening")) <= set(r) for r in a)
    assert all(set(("relations", "sub_claims", "mental_model")) <= set(r["deepening"]) for r in a)


def test_malformed_adapter_output_is_coerced():
    class Bad(deepen.Deepener):
        def deepen(self, text, context):
            return {"relations": "not-a-list", "sub_claims": None, "mental_model": 5, "junk": 1}
    v = deepen._valid(Bad().deepen("x", {}))
    assert v["relations"] == [] and v["sub_claims"] == [] and v["mental_model"] == {}


def test_promotion_requires_positive_verification_and_explicit_sink():
    records = deepen.deepen([_c("i1", "u:1", "U1", "Alpha; beta")],
                             deepener=deepen.EchoDeepener())
    retained = []
    plan = deepen.promote(records, verifier=lambda r: r["item_id"] == "i1",
                          sink=retained.append)
    assert plan["n_accepted"] == 1 and retained == records


def test_promotion_rejects_ungrounded_and_unverified_records():
    good = deepen.deepen([_c("i1", "u:1", "U1", "Alpha; beta")],
                          deepener=deepen.EchoDeepener())[0]
    bad = {**good, "canonical_urn": ""}
    plan = deepen.promotion_plan([good, bad], verifier=lambda r: False)
    assert plan["n_accepted"] == 0 and plan["n_rejected"] == 2
    assert {r["reason"] for r in plan["rejected"]} == {
        "verification-failed", "missing-source-identity"}
