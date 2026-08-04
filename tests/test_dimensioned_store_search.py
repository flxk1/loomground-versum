"""`from_dimensioned_store` — the DimensionedSubgraphSink store must be searchable
through the same `search_similar` ranking as the overlay/claims store (from_kg).

A folder ingested via the sink has NO claims.csv, so `from_kg` cannot see it; this builder
loads the signed transactions and emits one Doc per subgraph node instead.
"""
import hashlib

from versum.ingestion import SCHEMA, DimensionedSubgraphSink
from versum.store.retrieve import from_dimensioned_store


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _norm_node(node_id, *, statement, operator, bearer, action,
               incident="", condition="", exception="", deadline="", sanction=""):
    """A node in the persisted envelope shape: the deontic fields live under ``properties``
    (this is exactly how the ingest writer lowers a logical `kind="norm"` node)."""
    return {
        "node_id": node_id,
        "node_type": "norm",
        "dimensions": {"causal": "operator"},
        "properties": {
            "statement": statement, "operator": operator, "bearer": bearer,
            "action": action, "incident": incident, "condition": condition,
            "exception": exception, "deadline": deadline, "sanction": sanction,
            "provenance": {"source_sentence": statement},
        },
    }


def _envelope():
    return {
        "schema": SCHEMA,
        "idempotency_key": "ingest:regulation-1:v1",
        "source": {"source_id": "source:regulation-1", "content_digest": digest("reg")},
        "evidence": [{
            "evidence_id": "evidence:1",
            "source_id": "source:regulation-1",
            "locator": "art:5",
            "content_digest": digest("quotation"),
        }],
        "nd": {
            "facet": "5D",
            "system_id": "system:federation-5d",
            "dimension_count": 1,
            "axes": ["causal"],
        },
        "nodes": [
            _norm_node(
                "norm:controller-protection",
                statement="the controller must ensure protection of personal data",
                operator="obligation", bearer="controller", action="ensure protection",
                incident="duty", condition="when processing", sanction="administrative fine"),
            _norm_node(
                "norm:provider-register",
                statement="the provider shall register the high risk system",
                operator="obligation", bearer="provider", action="register system",
                incident="duty", deadline="before placing on the market"),
        ],
        "relations": [],
    }


def _write_store(tmp_path):
    authorized = tmp_path / "authorized"
    authorized.mkdir()
    store = authorized / "store"
    DimensionedSubgraphSink(store, authorized_store_root=authorized).upsert(_envelope())
    return store


def test_ingested_node_is_searchable_and_ranked(tmp_path):
    idx = from_dimensioned_store(_write_store(tmp_path))
    hits = idx.search_similar("controller protection personal data", k=5)
    assert hits and hits[0]["doc_id"] == "norm:controller-protection"
    scores = [h["score"] for h in hits]
    assert all(s > 0 for s in scores) and scores == sorted(scores, reverse=True)
    # canonical_urn is carried from the subgraph's source identifier.
    assert hits[0]["canonical_urn"] == "source:regulation-1"


def test_facet_values_contribute_to_overlap(tmp_path):
    idx = from_dimensioned_store(_write_store(tmp_path))
    # 'register' is in norm:provider-register's action (facet + text); the other node
    # never mentions it, so the query must surface exactly the register norm first.
    hits = idx.search_similar("register the system", k=5)
    assert hits and hits[0]["doc_id"] == "norm:provider-register"


def test_no_overlap_returns_nothing(tmp_path):
    idx = from_dimensioned_store(_write_store(tmp_path))
    assert idx.search_similar("wholly unrelated vocabulary", k=5) == []


def test_empty_store_returns_nothing(tmp_path):
    # A folder that was never written to by the sink has no transactions at all.
    empty = tmp_path / "empty"
    empty.mkdir()
    idx = from_dimensioned_store(empty)
    assert idx.docs == []
    assert idx.search_similar("controller data", k=5) == []
