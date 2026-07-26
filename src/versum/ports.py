"""Behavior ports for keeping Versum independent from any verifier implementation."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

#: Upper bound on one evidence batch (K4): a caller that needs more submits
#: more batches. The bound is part of the contract so no consumer can turn the
#: facade into an unbounded scan.
MAX_EVIDENCE_BATCH = 256


@runtime_checkable
class Verifier(Protocol):
    """Submit a vendor-neutral reasoning request to any conforming solver."""

    def manifest(self) -> dict:
        """Return a ``reasoning.interop`` protocol manifest."""
        ...

    def verify(self, request: dict) -> dict:
        """Return a versioned reasoning-result dictionary."""
        ...


@runtime_checkable
class EvidenceProvider(Protocol):
    """Resolve and verify stable evidence references against a knowledge store (K4).

    The scalar pair mirrors the Solver's ``EvidenceProvider`` port; the batch
    pair is the bounded-batch contract required before any high-throughput use.
    A batch is ordered, at most ``MAX_EVIDENCE_BATCH`` long, and its result
    aligns index-for-index with its input.
    """

    def resolve(self, ref) -> dict:
        """Return the evidence payload identified by ``ref``."""
        ...

    def verify(self, ref) -> bool:
        """Confirm source, item, span and digest consistency for ``ref``."""
        ...

    def resolve_batch(self, refs) -> list:
        """Resolve up to ``MAX_EVIDENCE_BATCH`` refs; unresolvable entries are None."""
        ...

    def verify_batch(self, refs) -> list:
        """Verify up to ``MAX_EVIDENCE_BATCH`` refs, index-aligned booleans."""
        ...

