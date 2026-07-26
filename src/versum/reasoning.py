"""Export grounded Versum claims to, and submit them through, a neutral protocol."""
from __future__ import annotations

from .interop import (
    Candidate, EvidenceRef, ProtocolManifest, ReasoningRequest, ReasoningResult,
    missing_capabilities, valid_graph_version,
)


def manifest(*, implementation_version="0.1.0", capabilities=None) -> dict:
    capabilities = tuple(capabilities or ("span-grounding", "structural-evidence"))
    return ProtocolManifest(
        implementation="loomground-versum",
        implementation_version=implementation_version,
        roles=("evidence-provider", "candidate-provider"),
        capabilities=capabilities,
        schemas={
            "source_signature": "loomground.versum.source-signature/v1",
            "claim_axes": "loomground.versum.claim-axes/v1",
        },
    ).to_dict()


def candidate_from_claim(row: dict, *, graph_version="", rank_metadata=None) -> Candidate:
    """Compile a materialized claim row without leaking Versum storage assumptions."""
    if not valid_graph_version(graph_version):
        # K2 seam obligation: results bind to a snapshot only if Versum mints
        # one, so a wire record needs a bounded, non-empty graph_version.
        # sync_once mints and stamps it; snapshot.require_graph_version obtains
        # it for store-backed emission (never invent the token).
        raise ValueError(
            "claim has no valid graph_version — obtain the stamped store token")
    source_id = (row.get("canonical_urn") or row.get("source_urn") or "").strip()
    item_id = (row.get("item_id") or "").strip()
    claim = str(row.get("text", "")).strip()
    if not source_id:
        raise ValueError("claim has no stable source identity")
    if not item_id:
        raise ValueError("claim has no item identity")
    if not claim:
        raise ValueError("claim text is empty")
    span_start = _int_or_none(row.get("span_start"))
    span_end = _int_or_none(row.get("span_end"))
    if ((span_start is None) != (span_end is None)
            or (span_start is not None and not 0 <= span_start < span_end)):
        raise ValueError("claim span is incomplete or invalid")
    digest = (row.get("content_digest") or row.get("sha256") or "").strip()
    if not digest and ":sha256:" in source_id:
        digest = "sha256:" + source_id.split(":sha256:", 1)[1]
    evidence = EvidenceRef(
        source_id=source_id,
        item_id=item_id,
        span_start=span_start,
        span_end=span_end,
        content_digest=digest,
        graph_version=graph_version,
        locator={"library": row.get("library", "")},
    )
    axes = {k: row[k] for k in (
        "predicate", "modality", "quantification", "polarity", "domain")
            if row.get(k) not in (None, "")}
    return Candidate(
        candidate_id=item_id or source_id,
        claim=claim,
        evidence=(evidence,),
        structural_evidence={"schema": "loomground.versum.claim-axes/v1", "axes": axes},
        producer="loomground-versum",
        producer_version="0.1.0",
        rank_metadata=dict(rank_metadata or {}),
    )


def request_from_claims(request_id: str, problem: dict, rows, *, graph_version="",
                        solver_profile="generic", required_capabilities=()) -> ReasoningRequest:
    candidates = tuple(candidate_from_claim(r, graph_version=graph_version) for r in rows)
    capabilities = ["span-grounding", "structural-evidence"]
    if candidates and all(e.content_digest for c in candidates for e in c.evidence):
        capabilities.append("content-digests")
    return ReasoningRequest(
        request_id=request_id,
        problem=problem,
        candidates=candidates,
        solver_profile=solver_profile,
        required_capabilities=tuple(required_capabilities),
        metadata={"producer_manifest": manifest(capabilities=capabilities)},
    )


def request_from_store(request_id: str, problem: dict, rows, *, kg_root,
                       solver_profile="generic", required_capabilities=()) -> ReasoningRequest:
    """Build a request whose snapshot identity comes from the store, not the caller.

    The 2026-07-21 review (finding 4): a producer emitting records for a store must
    obtain the ``graph_version`` from that store rather than accept an unconstrained
    argument. Raises when the store has never minted one.
    """
    from .snapshot import require_graph_version
    return request_from_claims(
        request_id, problem, rows,
        graph_version=require_graph_version(kg_root),
        solver_profile=solver_profile,
        required_capabilities=required_capabilities,
    )


def submit(verifier, request: ReasoningRequest) -> ReasoningResult:
    """Submit to any verifier port after role and capability negotiation."""
    remote = ProtocolManifest.from_dict(verifier.manifest())
    if "verifier" not in remote.roles:
        raise ValueError("peer does not advertise the verifier role")
    missing = missing_capabilities(remote, request.required_capabilities)
    if missing:
        return ReasoningResult(
            request_id=request.request_id,
            status="escalate",
            trace={"reason": "unsupported_capabilities", "missing": list(missing)},
            verifier=remote.implementation,
            verifier_version=remote.implementation_version,
        )
    result = ReasoningResult.from_dict(verifier.verify(request.to_dict()))
    if result.request_id != request.request_id:
        raise ValueError("verifier result does not match request_id")
    if result.verifier != remote.implementation or result.verifier_version != remote.implementation_version:
        raise ValueError("verifier result identity does not match advertised manifest")
    submitted = {c.candidate_id for c in request.candidates}
    accepted, undecided, rejected = set(result.accepted), set(result.undecided), set(result.rejected)
    decided = accepted | undecided | rejected
    if not decided <= submitted:
        raise ValueError("verifier result refers to unknown candidate IDs")
    if accepted & undecided or accepted & rejected or undecided & rejected:
        raise ValueError("verifier decision partitions overlap")
    if "signed-replay" in request.required_capabilities and not result.signature:
        raise ValueError("verifier advertised signed replay but returned no signature")
    return result


def _int_or_none(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
