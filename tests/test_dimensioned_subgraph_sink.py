import hashlib
import json

import pytest

from versum.ingestion import (
    DimensionedSubgraph,
    DimensionedSubgraphSink,
    IdempotencyConflictError,
    SCHEMA,
    SubgraphValidationError,
    load_dimensioned_subgraphs,
)
from versum.snapshot import mint_graph_version


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def envelope():
    return {
        "schema": SCHEMA,
        "idempotency_key": "ingest:document-1:v1",
        "source": {"source_id": "source:document-1", "content_digest": digest("document")},
        "evidence": [{
            "evidence_id": "evidence:1",
            "source_id": "source:document-1",
            "locator": "page:1",
            "content_digest": digest("quotation"),
        }],
        "nd": {
            "facet": "5D",
            "system_id": "system:federation-5d",
            "dimension_count": 2,
            "axes": ["relational", "contextual"],
        },
        "nodes": [
            {
                "node_id": "node:a",
                "node_type": "claim",
                "dimensions": {"relational": "subject", "contextual": "release"},
                "properties": {"text": "claim"},
            },
            {
                "node_id": "node:b",
                "node_type": "concept",
                "dimensions": {"relational": "object", "contextual": "release"},
                "properties": {"label": "concept"},
            },
        ],
        "relations": [{
            "relation_id": "relation:1",
            "relation_type": "supports",
            "source": {"kind": "node", "value": "node:a"},
            "target": {"kind": "node", "value": "node:b"},
            "dimension": "relational",
            "evidence_ids": ["evidence:1"],
            "properties": {},
        }],
    }


def test_atomic_upsert_and_idempotent_receipt(tmp_path):
    store = tmp_path / "authorized" / "store"
    authorized = tmp_path / "authorized"
    authorized.mkdir()
    sink = DimensionedSubgraphSink(store, authorized_store_root=authorized)

    first = sink.upsert(envelope())
    second = sink.upsert(envelope())

    assert first.status == "inserted"
    assert second.status == "unchanged"
    assert first.transaction_id == second.transaction_id
    transactions = list((store / "_dimensioned_subgraph_transactions").glob("*.json"))
    assert len(transactions) == 1
    persisted = json.loads(transactions[0].read_text())
    assert persisted["envelope"]["source"]["source_id"] == "source:document-1"
    assert load_dimensioned_subgraphs(store)[0].content_digest == first.content_digest
    version_with_graph = mint_graph_version(store)
    transactions[0].unlink()
    assert mint_graph_version(store) != version_with_graph
    assert not list(transactions[0].parent.glob(".subgraph-*"))


def test_idempotency_conflict_fails_closed(tmp_path):
    tmp_path.joinpath("authorized").mkdir()
    sink = DimensionedSubgraphSink(
        tmp_path / "authorized" / "store", authorized_store_root=tmp_path / "authorized"
    )
    sink.upsert(envelope())
    changed = envelope()
    changed["nodes"][0]["dimensions"]["contextual"] = "different"
    with pytest.raises(IdempotencyConflictError):
        sink.upsert(changed)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(schema="unknown/v1"),
        lambda value: value.update(unexpected=True),
        lambda value: value["nd"].update(dimension_count=3),
        lambda value: value["nodes"][0].update(dimensions={"undeclared": "subject"}),
        lambda value: value["relations"][0].update(
            target={"kind": "node", "value": "node:missing"}
        ),
        lambda value: value["relations"][0].update(evidence_ids=["evidence:missing"]),
        lambda value: value["evidence"][0].update(source_id="source:other"),
    ],
)
def test_malformed_envelopes_fail_closed(mutate):
    value = envelope()
    mutate(value)
    with pytest.raises(SubgraphValidationError):
        DimensionedSubgraph.from_dict(value)


def test_store_root_must_be_contained(tmp_path):
    authorized = tmp_path / "authorized"
    authorized.mkdir()
    with pytest.raises(PermissionError):
        DimensionedSubgraphSink(
            tmp_path / "other" / "store", authorized_store_root=authorized
        )


def test_adapter_projection_persistence_is_not_called(tmp_path, monkeypatch):
    authorized = tmp_path / "authorized"
    authorized.mkdir()

    def forbidden(*args, **kwargs):
        raise AssertionError("adapter projection persistence is a separate read-model door")

    monkeypatch.setattr("versum.adapters.save_projection", forbidden)
    receipt = DimensionedSubgraphSink(
        authorized / "store", authorized_store_root=authorized
    ).upsert(envelope())
    assert receipt.status == "inserted"
