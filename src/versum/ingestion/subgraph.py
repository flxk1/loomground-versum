"""Versioned Ingestor -> Versum dimensioned-subgraph write contract.

The transaction file written here is the canonical persistence record.  Adapter
projections are deliberately not involved: they are import/export materializations,
not an ingestion write door.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterator
from typing import Any, Mapping

SCHEMA = "loomground.versum.dimensioned-subgraph/v1"
RECEIPT_SCHEMA = "loomground.versum.dimensioned-subgraph-receipt/v1"
TRANSACTION_DIR = "_dimensioned_subgraph_transactions"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class SubgraphValidationError(ValueError):
    """The caller supplied an envelope Versum cannot safely persist."""


class IdempotencyConflictError(ValueError):
    """An idempotency key was already used for different semantic content."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SubgraphValidationError(f"{name} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    missing = expected - value.keys()
    extra = value.keys() - expected
    if missing or extra:
        raise SubgraphValidationError(
            f"{name} fields differ from contract; missing={sorted(missing)}, "
            f"extra={sorted(extra)}"
        )


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise SubgraphValidationError(f"{name} must be a non-empty contract identifier")
    return value


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise SubgraphValidationError(f"{name} must be a lowercase sha256 digest")
    return value


@dataclass(frozen=True)
class DimensionedSubgraph(Mapping[str, Any]):
    """Validated, immutable public ingestion envelope."""

    value: dict[str, Any]
    content_digest: str

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "DimensionedSubgraph":
        value = dict(_require_mapping(raw, "envelope"))
        _exact_keys(
            value,
            {"schema", "idempotency_key", "source", "evidence", "nd", "nodes", "relations"},
            "envelope",
        )
        if value["schema"] != SCHEMA:
            raise SubgraphValidationError(f"schema must be exactly {SCHEMA!r}")
        _identifier(value["idempotency_key"], "idempotency_key")

        source = _require_mapping(value["source"], "source")
        _exact_keys(source, {"source_id", "content_digest"}, "source")
        source_id = _identifier(source["source_id"], "source.source_id")
        _sha256(source["content_digest"], "source.content_digest")

        nd = _require_mapping(value["nd"], "nd")
        _exact_keys(nd, {"facet", "system_id", "dimension_count", "axes"}, "nd")
        if nd["facet"] not in {"5D", "nD"}:
            raise SubgraphValidationError("nd.facet must be exactly '5D' or 'nD'")
        _identifier(nd["system_id"], "nd.system_id")
        axes = nd["axes"]
        if not isinstance(axes, list) or not axes:
            raise SubgraphValidationError("nd.axes must be a non-empty array")
        axis_ids = [_identifier(axis, "nd.axes[]") for axis in axes]
        if len(set(axis_ids)) != len(axis_ids):
            raise SubgraphValidationError("nd.axes must be unique")
        if type(nd["dimension_count"]) is not int or nd["dimension_count"] != len(axis_ids):
            raise SubgraphValidationError("nd.dimension_count must equal len(nd.axes)")

        evidence = value["evidence"]
        if not isinstance(evidence, list) or not evidence:
            raise SubgraphValidationError("evidence must be a non-empty array")
        evidence_ids: set[str] = set()
        for index, item in enumerate(evidence):
            item = _require_mapping(item, f"evidence[{index}]")
            _exact_keys(item, {"evidence_id", "source_id", "locator", "content_digest"},
                        f"evidence[{index}]")
            evidence_id = _identifier(item["evidence_id"], f"evidence[{index}].evidence_id")
            if evidence_id in evidence_ids:
                raise SubgraphValidationError("evidence ids must be unique")
            evidence_ids.add(evidence_id)
            if item["source_id"] != source_id:
                raise SubgraphValidationError("all evidence must bind to envelope source_id")
            if not isinstance(item["locator"], str) or not item["locator"]:
                raise SubgraphValidationError("evidence locator must be a non-empty string")
            _sha256(item["content_digest"], f"evidence[{index}].content_digest")

        nodes = value["nodes"]
        if not isinstance(nodes, list) or not nodes:
            raise SubgraphValidationError("nodes must be a non-empty array")
        node_ids: set[str] = set()
        for index, node in enumerate(nodes):
            node = _require_mapping(node, f"nodes[{index}]")
            _exact_keys(
                node, {"node_id", "node_type", "dimensions", "properties"}, f"nodes[{index}]"
            )
            node_id = _identifier(node["node_id"], f"nodes[{index}].node_id")
            if node_id in node_ids:
                raise SubgraphValidationError("node ids must be unique")
            node_ids.add(node_id)
            _identifier(node["node_type"], f"nodes[{index}].node_type")
            _require_mapping(node["properties"], f"nodes[{index}].properties")
            dimensions = _require_mapping(node["dimensions"], f"nodes[{index}].dimensions")
            if not set(dimensions).issubset(axis_ids):
                raise SubgraphValidationError("node dimensions must name declared nD axes")
            for axis, coordinate in dimensions.items():
                if not isinstance(coordinate, (str, int, float, bool)) or coordinate is None:
                    raise SubgraphValidationError(
                        f"node dimension {axis!r} must be a scalar JSON value"
                    )

        relations = value["relations"]
        if not isinstance(relations, list):
            raise SubgraphValidationError("relations must be an array")
        relation_ids: set[str] = set()
        for index, relation in enumerate(relations):
            relation = _require_mapping(relation, f"relations[{index}]")
            _exact_keys(
                relation,
                {"relation_id", "relation_type", "source", "target",
                 "dimension", "evidence_ids", "properties"},
                f"relations[{index}]",
            )
            relation_id = _identifier(
                relation["relation_id"], f"relations[{index}].relation_id"
            )
            if relation_id in relation_ids:
                raise SubgraphValidationError("relation ids must be unique")
            relation_ids.add(relation_id)
            _identifier(relation["relation_type"], f"relations[{index}].relation_type")
            for endpoint_name in ("source", "target"):
                endpoint = _require_mapping(
                    relation[endpoint_name], f"relations[{index}].{endpoint_name}"
                )
                _exact_keys(endpoint, {"kind", "value"}, f"relations[{index}].{endpoint_name}")
                if endpoint["kind"] not in {"node", "literal"}:
                    raise SubgraphValidationError("relation endpoint kind must be node or literal")
                if endpoint["kind"] == "node":
                    if endpoint["value"] not in node_ids:
                        raise SubgraphValidationError("node relation endpoint is unknown")
                elif not isinstance(endpoint["value"], (str, int, float, bool)):
                    raise SubgraphValidationError("literal relation endpoint must be scalar")
            if relation["dimension"] not in axis_ids:
                raise SubgraphValidationError("relation dimension must name an nD axis")
            refs = relation["evidence_ids"]
            if not isinstance(refs, list) or not refs or not all(ref in evidence_ids for ref in refs):
                raise SubgraphValidationError("relations require known evidence_ids")
            if len(set(refs)) != len(refs):
                raise SubgraphValidationError("relation evidence_ids must be unique")
            _require_mapping(relation["properties"], f"relations[{index}].properties")

        # Round-trip through JSON rejects custom Mapping/scalar subclasses and gives
        # callers an immutable-by-convention copy owned by the envelope.
        normalized = json.loads(_canonical_bytes(value))
        return cls(normalized, _digest(normalized))

    def to_dict(self) -> dict[str, Any]:
        return json.loads(_canonical_bytes(self.value))

    def __getitem__(self, key: str) -> Any:
        return self.value[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.value)

    def __len__(self) -> int:
        return len(self.value)


@dataclass(frozen=True)
class UpsertReceipt(Mapping[str, Any]):
    schema: str
    idempotency_key: str
    content_digest: str
    transaction_id: str
    status: str

    def to_dict(self) -> dict[str, str]:
        return {
            "schema": self.schema,
            "idempotency_key": self.idempotency_key,
            "content_digest": self.content_digest,
            "transaction_id": self.transaction_id,
            "status": self.status,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())


class DimensionedSubgraphSink:
    """Authorized, idempotent and atomic canonical Versum ingestion sink."""

    def __init__(self, store_root: str | Path, *, authorized_store_root: str | Path):
        authorized = Path(authorized_store_root).resolve(strict=True)
        root = Path(store_root).resolve(strict=False)
        if root != authorized and authorized not in root.parents:
            raise PermissionError("store_root is outside authorized_store_root")
        root.mkdir(parents=True, exist_ok=True)
        # Resolve again after creation to close symlink-based containment changes.
        resolved = root.resolve(strict=True)
        if resolved != authorized and authorized not in resolved.parents:
            raise PermissionError("resolved store_root is outside authorized_store_root")
        self.root = resolved

    def upsert(self, envelope: DimensionedSubgraph | Mapping[str, Any]) -> UpsertReceipt:
        graph = (
            envelope
            if isinstance(envelope, DimensionedSubgraph)
            else DimensionedSubgraph.from_dict(envelope)
        )
        key = graph.value["idempotency_key"]
        transaction_id = "subgraph:" + hashlib.sha256(key.encode("utf-8")).hexdigest()
        target_dir = self.root / TRANSACTION_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{transaction_id.removeprefix('subgraph:')}.json"
        transaction = {
            "schema": "loomground.versum.dimensioned-subgraph-transaction/v1",
            "transaction_id": transaction_id,
            "idempotency_key": key,
            "content_digest": graph.content_digest,
            "envelope": graph.to_dict(),
        }
        if target.exists():
            persisted = json.loads(target.read_text(encoding="utf-8"))
            if persisted != transaction:
                raise IdempotencyConflictError(
                    f"idempotency key {key!r} is already bound to different content"
                )
            return UpsertReceipt(
                RECEIPT_SCHEMA, key, graph.content_digest, transaction_id, "unchanged"
            )

        fd, temporary = tempfile.mkstemp(prefix=".subgraph-", dir=target_dir)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(_canonical_bytes(transaction) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            # An exclusive hard-link publishes the complete canonical transaction
            # without allowing concurrent writers to replace one another.
            try:
                os.link(temporary, target)
            except FileExistsError:
                persisted = json.loads(target.read_text(encoding="utf-8"))
                if persisted != transaction:
                    raise IdempotencyConflictError(
                        f"idempotency key {key!r} is already bound to different content"
                    ) from None
                return UpsertReceipt(
                    RECEIPT_SCHEMA, key, graph.content_digest, transaction_id, "unchanged"
                )
            directory_fd = os.open(target_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return UpsertReceipt(
            RECEIPT_SCHEMA, key, graph.content_digest, transaction_id, "inserted"
        )


def load_dimensioned_subgraphs(store_root: str | Path) -> tuple[DimensionedSubgraph, ...]:
    """Read and revalidate canonical subgraph transactions for graph consumers."""
    directory = Path(store_root).resolve(strict=True) / TRANSACTION_DIR
    if not directory.exists():
        return ()
    graphs = []
    for path in sorted(directory.glob("*.json")):
        transaction = json.loads(path.read_text(encoding="utf-8"))
        expected = {
            "schema", "transaction_id", "idempotency_key", "content_digest", "envelope"
        }
        if not isinstance(transaction, dict) or set(transaction) != expected:
            raise SubgraphValidationError(f"invalid canonical transaction {path.name}")
        if transaction["schema"] != "loomground.versum.dimensioned-subgraph-transaction/v1":
            raise SubgraphValidationError(f"unknown transaction schema in {path.name}")
        graph = DimensionedSubgraph.from_dict(transaction["envelope"])
        if graph.content_digest != transaction["content_digest"]:
            raise SubgraphValidationError(f"transaction digest mismatch in {path.name}")
        if graph.value["idempotency_key"] != transaction["idempotency_key"]:
            raise SubgraphValidationError(f"transaction key mismatch in {path.name}")
        expected_id = "subgraph:" + hashlib.sha256(
            transaction["idempotency_key"].encode("utf-8")
        ).hexdigest()
        if transaction["transaction_id"] != expected_id:
            raise SubgraphValidationError(f"transaction identity mismatch in {path.name}")
        graphs.append(graph)
    return tuple(graphs)
