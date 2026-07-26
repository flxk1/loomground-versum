"""Workspace intake and deterministic ingestion pipeline.

One inbox per workspace. Pass 0 (acquire) turns a dropped file or a submitted URL into
either a local artifact ready for provenance, or a citation-only record when the bytes
cannot be had yet. Nothing here names a domain; identity comes from the engine.

The public dimensioned-subgraph types below form the post-acquisition Ingestor → Versum
contract.
"""

from .subgraph import (
    RECEIPT_SCHEMA,
    SCHEMA,
    DimensionedSubgraph,
    DimensionedSubgraphSink,
    IdempotencyConflictError,
    SubgraphValidationError,
    UpsertReceipt,
    load_dimensioned_subgraphs,
)

__all__ = [
    "RECEIPT_SCHEMA",
    "SCHEMA",
    "DimensionedSubgraph",
    "DimensionedSubgraphSink",
    "IdempotencyConflictError",
    "SubgraphValidationError",
    "UpsertReceipt",
    "load_dimensioned_subgraphs",
]
