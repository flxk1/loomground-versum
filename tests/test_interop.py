import hashlib
import json

from versum.interop import (
    ProtocolManifest, ReasoningRequest, ReasoningResult,
)
from versum.reasoning import candidate_from_claim, request_from_claims, submit


# A real digest (of the fixture's notional source content): the Solver rejects
# anything that is not sha256 + 64 hex chars, so the fixture must be wire-valid.
DIGEST = "sha256:" + hashlib.sha256(b"A grounded claim, in context.").hexdigest()

ROW = {
    "canonical_urn": "urn:any:source:1",
    "item_id": "claim-1",
    "text": "A grounded claim",
    "span_start": "4",
    "span_end": "19",
    "sha256": DIGEST,
    "predicate": "supports",
    "domain": "example",
}


def test_claim_compiles_to_vendor_neutral_candidate():
    c = candidate_from_claim(ROW, graph_version="graph-7", rank_metadata={"bm25": 0.8})
    assert c.evidence[0].source_id == "urn:any:source:1"
    assert c.evidence[0].span_start == 4
    assert c.structural_evidence["axes"]["predicate"] == "supports"
    assert c.rank_metadata == {"bm25": 0.8}


def test_request_wire_roundtrip_is_json_safe():
    req = request_from_claims("r1", {"text": "Question"}, [ROW], graph_version="g1")
    wire = json.loads(json.dumps(req.to_dict()))
    assert ReasoningRequest.from_dict(wire) == req
    assert wire["protocol"] == "reasoning.interop"


def test_submit_works_with_any_conforming_verifier():
    class Verifier:
        def manifest(self):
            return ProtocolManifest("other-solver", "3", ("verifier",),
                                    ("candidate-adjudication",)).to_dict()

        def verify(self, wire):
            req = ReasoningRequest.from_dict(wire)
            return ReasoningResult(req.request_id, "complete",
                                   accepted=(req.candidates[0].candidate_id,),
                                   verifier="other-solver", verifier_version="3").to_dict()

    req = request_from_claims("r1", {"text": "Question"}, [ROW], graph_version="g1",
                              required_capabilities=("candidate-adjudication",))
    result = submit(Verifier(), req)
    assert result.accepted == ("claim-1",)


def test_submit_escalates_before_calling_incapable_verifier():
    class Incapable:
        def manifest(self):
            return ProtocolManifest("minimal", "1", ("verifier",), ()).to_dict()

        def verify(self, wire):
            raise AssertionError("must not dispatch")

    req = request_from_claims("r1", {}, [ROW], graph_version="g1",
                              required_capabilities=("signed-replay",))
    result = submit(Incapable(), req)
    assert result.status == "escalate"
    assert result.trace["missing"] == ["signed-replay"]


def test_candidate_rejects_ungrounded_or_invalid_claims():
    import pytest
    for patch in ({"canonical_urn": ""}, {"item_id": ""}, {"text": ""},
                  {"span_start": "20", "span_end": "4"}):
        row = {**ROW, **patch}
        with pytest.raises(ValueError):
            candidate_from_claim(row, graph_version="g1")


def test_candidate_requires_a_valid_graph_version_token():
    # K2: a wire record needs a bounded, non-empty graph_version — results can
    # only bind to a snapshot Versum actually minted (interop.valid_graph_version).
    import pytest
    from versum.interop import MAX_GRAPH_VERSION_LENGTH
    for bad in ("", "   ", "x" * (MAX_GRAPH_VERSION_LENGTH + 1)):
        with pytest.raises(ValueError, match="graph_version"):
            candidate_from_claim(ROW, graph_version=bad)
    with pytest.raises(ValueError, match="graph_version"):
        request_from_claims("r1", {}, [ROW])


def test_content_digest_capability_is_advertised_only_when_present():
    hashed = {**ROW, "canonical_urn": "urn:any:" + DIGEST, "sha256": ""}
    req = request_from_claims("r1", {}, [hashed], graph_version="g1")
    assert "content-digests" in req.metadata["producer_manifest"]["capabilities"]
    canonical = {**ROW, "canonical_urn": "urn:any:doi:10.1/x", "sha256": ""}
    req = request_from_claims("r2", {}, [canonical], graph_version="g1")
    assert "content-digests" not in req.metadata["producer_manifest"]["capabilities"]


def test_submit_rejects_uncorrelated_or_invalid_result():
    import pytest

    class Bad:
        def manifest(self):
            return ProtocolManifest("bad", "1", ("verifier",),
                                    ("candidate-adjudication",)).to_dict()

        def verify(self, wire):
            return ReasoningResult("wrong-request", "complete", accepted=("unknown",),
                                   verifier="bad", verifier_version="1").to_dict()

    req = request_from_claims("r1", {}, [ROW], graph_version="g1",
                              required_capabilities=("candidate-adjudication",))
    with pytest.raises(ValueError, match="request_id"):
        submit(Bad(), req)


def test_submit_rejects_overlapping_decision_partitions():
    import pytest

    class Bad:
        def manifest(self):
            return ProtocolManifest("bad", "1", ("verifier",), ()).to_dict()

        def verify(self, wire):
            req = ReasoningRequest.from_dict(wire)
            cid = req.candidates[0].candidate_id
            return ReasoningResult(req.request_id, "complete", accepted=(cid,),
                                   undecided=(cid,), verifier="bad", verifier_version="1").to_dict()

    with pytest.raises(ValueError, match="overlap"):
        submit(Bad(), request_from_claims("r1", {}, [ROW], graph_version="g1"))


def test_wire_decode_rejects_missing_or_oversize_graph_version():
    # Finding 4 (2026-07-21 review): non-empty-at-one-producer-helper is not the
    # invariant — the wire decoder itself must refuse an unbound evidence ref.
    import pytest
    from versum.interop import EvidenceRef, MAX_GRAPH_VERSION_LENGTH
    good = candidate_from_claim(ROW, graph_version="g1").evidence[0].to_dict()
    assert EvidenceRef.from_dict(good).graph_version == "g1"
    for bad in ("", "   ", "x" * (MAX_GRAPH_VERSION_LENGTH + 1)):
        with pytest.raises(ValueError, match="graph_version"):
            EvidenceRef.from_dict({**good, "graph_version": bad})
    with pytest.raises(ValueError, match="graph_version"):
        ReasoningRequest.from_dict(
            request_from_claims("r1", {}, [ROW], graph_version="g1").to_dict()
            | {"candidates": [{**candidate_from_claim(ROW, graph_version="g1").to_dict(),
                               "evidence": [{**good, "graph_version": ""}]}]})


def test_request_from_store_takes_the_stamped_token_not_a_caller_argument(tmp_path):
    # Finding 4: a store-backed producer obtains graph_version from the store.
    import pytest
    from versum.reasoning import request_from_store
    from versum.snapshot import stamp_graph_version
    with pytest.raises(ValueError, match="graph_version"):
        request_from_store("r1", {}, [ROW], kg_root=tmp_path)  # never synced
    stamp_graph_version(tmp_path, "sha256:" + "0" * 64)
    req = request_from_store("r1", {}, [ROW], kg_root=tmp_path)
    assert req.candidates[0].evidence[0].graph_version == "sha256:" + "0" * 64
