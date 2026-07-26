# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flxk1
"""Vendor-neutral wire records for graph/verifier interoperability.

This module is deliberately data-only and stdlib-only. Any graph, corpus,
retriever, generator, or solver can implement the protocol without importing a
particular product. The wire representation is plain JSON-safe dictionaries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


PROTOCOL = "reasoning.interop"
PROTOCOL_VERSION = "1.0"

#: Wire bound on a snapshot identifier: a decoded evidence ref must carry a non-empty
#: ``graph_version`` of at most this many characters. The token stays opaque — the
#: bound and non-emptiness are the only spec-level constraints (2026-07-21 review,
#: finding 4: presence at one producer helper is not decode-time enforcement).
MAX_GRAPH_VERSION_LENGTH = 256


def valid_graph_version(token) -> bool:
    """True when ``token`` is a wire-valid snapshot identifier."""
    return (isinstance(token, str) and bool(token.strip())
            and len(token) <= MAX_GRAPH_VERSION_LENGTH)


def _require_version(data: Mapping[str, Any]) -> None:
    if data.get("protocol") != PROTOCOL:
        raise ValueError("unsupported interoperability protocol")
    if data.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("incompatible interoperability protocol version")


def missing_capabilities(manifest: "ProtocolManifest", required) -> tuple[str, ...]:
    """Return required capabilities not advertised by an implementation."""
    offered = set(manifest.capabilities)
    return tuple(sorted(set(required) - offered))


@dataclass(frozen=True)
class EvidenceRef:
    """Stable reference to exact evidence; never a filesystem-derived identity."""

    source_id: str
    item_id: str = ""
    span_start: int | None = None
    span_end: int | None = None
    content_digest: str = ""
    graph_version: str = ""
    locator: Mapping[str, Any] = field(default_factory=dict)
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "item_id": self.item_id,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "content_digest": self.content_digest,
            "graph_version": self.graph_version,
            "locator": dict(self.locator),
            "extensions": dict(self.extensions),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceRef":
        graph_version = str(data.get("graph_version", ""))
        if not valid_graph_version(graph_version):
            raise ValueError(
                "evidence ref must carry a non-empty graph_version of at most "
                f"{MAX_GRAPH_VERSION_LENGTH} characters")
        return cls(
            source_id=str(data.get("source_id", "")),
            item_id=str(data.get("item_id", "")),
            span_start=data.get("span_start"),
            span_end=data.get("span_end"),
            content_digest=str(data.get("content_digest", "")),
            graph_version=graph_version,
            locator=dict(data.get("locator", {})),
            extensions=dict(data.get("extensions", {})),
        )


@dataclass(frozen=True)
class ProtocolManifest:
    """Advertise an implementation's roles, schemas and optional capabilities."""

    implementation: str
    implementation_version: str
    roles: tuple[str, ...]
    capabilities: tuple[str, ...] = ()
    schemas: Mapping[str, str] = field(default_factory=dict)
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "protocol": PROTOCOL,
            "protocol_version": PROTOCOL_VERSION,
            "kind": "manifest",
            "implementation": self.implementation,
            "implementation_version": self.implementation_version,
            "roles": list(self.roles),
            "capabilities": list(self.capabilities),
            "schemas": dict(self.schemas),
            "extensions": dict(self.extensions),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProtocolManifest":
        _require_version(data)
        if data.get("kind") != "manifest":
            raise ValueError("not a protocol manifest")
        return cls(
            implementation=str(data.get("implementation", "")),
            implementation_version=str(data.get("implementation_version", "")),
            roles=tuple(data.get("roles", ())),
            capabilities=tuple(data.get("capabilities", ())),
            schemas=dict(data.get("schemas", {})),
            extensions=dict(data.get("extensions", {})),
        )


@dataclass(frozen=True)
class Candidate:
    """Untrusted proposal with its grounding and optional structural evidence."""

    candidate_id: str
    claim: str
    evidence: tuple[EvidenceRef, ...] = ()
    structural_evidence: Mapping[str, Any] = field(default_factory=dict)
    producer: str = ""
    producer_version: str = ""
    rank_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "claim": self.claim,
            "evidence": [e.to_dict() for e in self.evidence],
            "structural_evidence": dict(self.structural_evidence),
            "producer": self.producer,
            "producer_version": self.producer_version,
            "rank_metadata": dict(self.rank_metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Candidate":
        return cls(
            candidate_id=str(data.get("candidate_id", "")),
            claim=str(data.get("claim", "")),
            evidence=tuple(EvidenceRef.from_dict(e) for e in data.get("evidence", ())),
            structural_evidence=dict(data.get("structural_evidence", {})),
            producer=str(data.get("producer", "")),
            producer_version=str(data.get("producer_version", "")),
            rank_metadata=dict(data.get("rank_metadata", {})),
        )


@dataclass(frozen=True)
class ReasoningRequest:
    """Knowledge-provider-neutral request submitted to a verifier."""

    request_id: str
    problem: Mapping[str, Any]
    candidates: tuple[Candidate, ...] = ()
    solver_profile: str = "generic"
    required_capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "protocol": PROTOCOL,
            "protocol_version": PROTOCOL_VERSION,
            "kind": "reasoning_request",
            "request_id": self.request_id,
            "problem": dict(self.problem),
            "candidates": [c.to_dict() for c in self.candidates],
            "solver_profile": self.solver_profile,
            "required_capabilities": list(self.required_capabilities),
            "metadata": dict(self.metadata),
            "extensions": dict(self.extensions),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReasoningRequest":
        _require_version(data)
        if data.get("kind") != "reasoning_request":
            raise ValueError("not a reasoning request")
        return cls(
            request_id=str(data.get("request_id", "")),
            problem=dict(data.get("problem", {})),
            candidates=tuple(Candidate.from_dict(c) for c in data.get("candidates", ())),
            solver_profile=str(data.get("solver_profile", "generic")),
            required_capabilities=tuple(data.get("required_capabilities", ())),
            metadata=dict(data.get("metadata", {})),
            extensions=dict(data.get("extensions", {})),
        )


@dataclass(frozen=True)
class ReasoningResult:
    """Verifier result returned to a producer; the producer controls retention."""

    request_id: str
    status: str
    accepted: tuple[str, ...] = ()
    undecided: tuple[str, ...] = ()
    rejected: Mapping[str, str] = field(default_factory=dict)
    trace: Mapping[str, Any] = field(default_factory=dict)
    verifier: str = ""
    verifier_version: str = ""
    signature: str = ""
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "protocol": PROTOCOL,
            "protocol_version": PROTOCOL_VERSION,
            "kind": "reasoning_result",
            "request_id": self.request_id,
            "status": self.status,
            "accepted": list(self.accepted),
            "undecided": list(self.undecided),
            "rejected": dict(self.rejected),
            "trace": dict(self.trace),
            "verifier": self.verifier,
            "verifier_version": self.verifier_version,
            "signature": self.signature,
            "extensions": dict(self.extensions),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReasoningResult":
        _require_version(data)
        if data.get("kind") != "reasoning_result":
            raise ValueError("not a reasoning result")
        return cls(
            request_id=str(data.get("request_id", "")),
            status=str(data.get("status", "")),
            accepted=tuple(data.get("accepted", ())),
            undecided=tuple(data.get("undecided", ())),
            rejected=dict(data.get("rejected", {})),
            trace=dict(data.get("trace", {})),
            verifier=str(data.get("verifier", "")),
            verifier_version=str(data.get("verifier_version", "")),
            signature=str(data.get("signature", "")),
            extensions=dict(data.get("extensions", {})),
        )
