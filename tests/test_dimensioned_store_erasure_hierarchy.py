"""Erasure, distribution and folder-hierarchy awareness over the dimensioned-subgraph SINK
store — the symmetric counterpart of the claims-store paths.

The claims/overlay store already honours erasure, distribution and the asymmetric folder
hierarchy (see test_store_erasure / test_store_hierarchy). These tests prove the *sink* store
— the signed transactions written by :class:`DimensionedSubgraphSink` — honours the same three,
through the same public entry points:

  * ``erasure.delete / restore / purge`` addressed with the ``"sink:"`` node-id convention,
  * ``erasure.delete_by_source / purge_by_source`` keyed by the subgraph ``source.source_id``,
  * ``distribution.publish / unpublish`` for sink nodes,
  * ``hierarchy.from_dimensioned_folder`` — own + descendants + ancestor-published, erasure-aware.
"""
import hashlib

import pytest

from versum.ingestion import SCHEMA, DimensionedSubgraphSink
from versum.store import distribution, erasure, hierarchy
from versum.store.retrieve import from_dimensioned_store


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _norm_node(node_id, *, statement, bearer, action):
    """A persisted-envelope node (deontic fields live under ``properties``)."""
    return {
        "node_id": node_id,
        "node_type": "norm",
        "dimensions": {"causal": "operator"},
        "properties": {
            "statement": statement, "operator": "obligation", "bearer": bearer,
            "action": action, "incident": "duty", "condition": "", "exception": "",
            "deadline": "", "sanction": "",
            "provenance": {"source_sentence": statement},
        },
    }


def _envelope(*, idempotency_key, source_id, nodes):
    """Build a valid one-source subgraph envelope carrying ``nodes`` (each a _norm_node)."""
    return {
        "schema": SCHEMA,
        "idempotency_key": idempotency_key,
        "source": {"source_id": source_id, "content_digest": digest(source_id)},
        "evidence": [{
            "evidence_id": "evidence:1",
            "source_id": source_id,
            "locator": "art:5",
            "content_digest": digest("quotation:" + source_id),
        }],
        "nd": {
            "facet": "5D", "system_id": "system:federation-5d",
            "dimension_count": 1, "axes": ["causal"],
        },
        "nodes": nodes,
        "relations": [],
    }


def _write(store_root, authorized_root, envelope):
    DimensionedSubgraphSink(store_root, authorized_store_root=authorized_root).upsert(envelope)


def _two_node_store(tmp_path):
    """A single sink store (one source, two nodes) for node/source erasure tests."""
    authorized = tmp_path / "authorized"
    authorized.mkdir()
    store = authorized / "store"
    _write(store, authorized, _envelope(
        idempotency_key="ingest:reg-1:v1",
        source_id="source:regulation-1",
        nodes=[
            _norm_node("norm:controller-protection",
                       statement="the controller must ensure protection of personal data",
                       bearer="controller", action="ensure protection"),
            _norm_node("norm:provider-register",
                       statement="the provider shall register the high risk system",
                       bearer="provider", action="register system"),
        ]))
    return store


def _doc_ids(hits):
    return {h["doc_id"] for h in hits}


# ── node-level erasure over the sink store ────────────────────────
def test_sink_delete_hides_node_then_restore_brings_it_back(tmp_path):
    store = _two_node_store(tmp_path)
    assert "norm:controller-protection" in _doc_ids(
        from_dimensioned_store(store).search_similar("controller protection data", k=5))

    erasure.delete(store, "sink:norm:controller-protection", reason="gdpr")
    hits = from_dimensioned_store(store).search_similar("controller protection data", k=5)
    assert "norm:controller-protection" not in _doc_ids(hits)
    # the sibling node in the same subgraph is untouched.
    assert "norm:provider-register" in _doc_ids(
        from_dimensioned_store(store).search_similar("register system", k=5))

    erasure.restore(store, "sink:norm:controller-protection")
    hits = from_dimensioned_store(store).search_similar("controller protection data", k=5)
    assert "norm:controller-protection" in _doc_ids(hits)


def test_tombstones_hides_matches_sink_doc_directly(tmp_path):
    store = _two_node_store(tmp_path)
    erasure.delete(store, "sink:norm:controller-protection")
    tombs = erasure.load_tombstones(store)
    # doc_id is the RAW node_id; the tombstone is keyed by it, so hides() matches directly.
    assert tombs.hides("norm:controller-protection", "source:regulation-1")
    assert not tombs.hides("norm:provider-register", "source:regulation-1")


def test_sink_purge_is_physical_and_irrecoverable(tmp_path):
    store = _two_node_store(tmp_path)
    result = erasure.purge(store, "sink:norm:controller-protection", reason="art17")
    assert result["grade"] == "purged" and result["rows_removed"] == 1

    # gone from search, and physically gone from the reloaded transaction.
    hits = from_dimensioned_store(store).search_similar("controller protection data", k=5)
    assert "norm:controller-protection" not in _doc_ids(hits)
    from versum.ingestion.subgraph import load_dimensioned_subgraphs
    remaining = {n["node_id"] for g in load_dimensioned_subgraphs(store) for n in g["nodes"]}
    assert remaining == {"norm:provider-register"}

    # a purge is not recoverable.
    with pytest.raises(ValueError):
        erasure.restore(store, "sink:norm:controller-protection")


def test_sink_purge_of_last_node_drops_the_transaction(tmp_path):
    authorized = tmp_path / "authorized"
    authorized.mkdir()
    store = authorized / "store"
    _write(store, authorized, _envelope(
        idempotency_key="ingest:solo:v1", source_id="source:solo",
        nodes=[_norm_node("norm:solo", statement="a lone obligation",
                          bearer="one", action="do")]))
    erasure.purge(store, "sink:norm:solo")
    from versum.ingestion.subgraph import load_dimensioned_subgraphs
    assert load_dimensioned_subgraphs(store) == ()


# ── source-level erasure over the sink store ──────────────────────
def test_sink_delete_by_source_drops_all_of_a_sources_nodes(tmp_path):
    store = _two_node_store(tmp_path)
    erasure.delete_by_source(store, "source:regulation-1", reason="gdpr")
    idx = from_dimensioned_store(store)
    assert idx.search_similar("controller protection data", k=5) == []
    assert idx.search_similar("register system", k=5) == []
    # source-level delete is recoverable.
    erasure.restore_source(store, "source:regulation-1")
    assert from_dimensioned_store(store).search_similar("register system", k=5)


def test_sink_purge_by_source_physically_removes_the_subgraph(tmp_path):
    store = _two_node_store(tmp_path)
    result = erasure.purge_by_source(store, "source:regulation-1", reason="art17")
    assert result["rows_removed"] == 2
    from versum.ingestion.subgraph import load_dimensioned_subgraphs
    assert load_dimensioned_subgraphs(store) == ()


# ── folder-hierarchy-aware sink search ────────────────────────────
def _folder_store(folder, tmp_path, *, idempotency_key, source_id, nodes):
    """Write a sink store into ``<folder>/.versum`` (the per-folder kg_root)."""
    folder.mkdir(parents=True, exist_ok=True)
    _write(folder / hierarchy.VERSUM_DIRNAME, tmp_path,
           _envelope(idempotency_key=idempotency_key, source_id=source_id, nodes=nodes))


def test_descendant_sink_node_appears_in_parents_hierarchy_search(tmp_path):
    parent = tmp_path / "acme"
    child = parent / "engineering"
    _folder_store(parent, tmp_path, idempotency_key="ingest:p:v1",
                  source_id="source:parent",
                  nodes=[_norm_node("norm:parent-policy",
                                    statement="the org must keep records",
                                    bearer="org", action="keep records")])
    _folder_store(child, tmp_path, idempotency_key="ingest:c:v1",
                  source_id="source:child",
                  nodes=[_norm_node("norm:child-rule",
                                    statement="engineers must log deployments",
                                    bearer="engineer", action="log deployments")])

    # the parent sees its own node AND the descendant's (memory flows UP).
    parent_hits = hierarchy.from_dimensioned_folder(parent).search_similar(
        "engineers log deployments", k=5)
    assert "norm:child-rule" in _doc_ids(parent_hits)

    # the child never reads a private ancestor node (nothing published) — DOWN is filtered.
    child_hits = hierarchy.from_dimensioned_folder(child).search_similar(
        "org keep records", k=5)
    assert "norm:parent-policy" not in _doc_ids(child_hits)


def test_ancestor_published_sink_node_flows_down_unpublished_does_not(tmp_path):
    parent = tmp_path / "acme"
    child = parent / "engineering"
    _folder_store(parent, tmp_path, idempotency_key="ingest:p2:v1",
                  source_id="source:parent2",
                  nodes=[
                      _norm_node("norm:shared-standard",
                                 statement="all teams must encrypt data at rest",
                                 bearer="team", action="encrypt data"),
                      _norm_node("norm:private-note",
                                 statement="the board reviews budget quarterly",
                                 bearer="board", action="review budget"),
                  ])
    _folder_store(child, tmp_path, idempotency_key="ingest:c2:v1",
                  source_id="source:child2",
                  nodes=[_norm_node("norm:child-only",
                                    statement="engineers rotate keys monthly",
                                    bearer="engineer", action="rotate keys")])

    parent_root = parent / hierarchy.VERSUM_DIRNAME
    distribution.publish(parent_root, "sink:norm:shared-standard")

    idx = hierarchy.from_dimensioned_folder(child)
    assert "norm:shared-standard" in _doc_ids(idx.search_similar("encrypt data at rest", k=5))
    assert "norm:private-note" not in _doc_ids(idx.search_similar("board review budget", k=5))

    # unpublish revokes the downward flow.
    distribution.unpublish(parent_root, "sink:norm:shared-standard")
    idx = hierarchy.from_dimensioned_folder(child)
    assert "norm:shared-standard" not in _doc_ids(idx.search_similar("encrypt data at rest", k=5))


def test_erased_ancestor_node_is_never_distributed(tmp_path):
    parent = tmp_path / "acme"
    child = parent / "engineering"
    _folder_store(parent, tmp_path, idempotency_key="ingest:p3:v1",
                  source_id="source:parent3",
                  nodes=[_norm_node("norm:erased-shared",
                                    statement="all teams must encrypt data at rest",
                                    bearer="team", action="encrypt data")])
    _folder_store(child, tmp_path, idempotency_key="ingest:c3:v1",
                  source_id="source:child3",
                  nodes=[_norm_node("norm:child-node",
                                    statement="engineers rotate keys",
                                    bearer="engineer", action="rotate keys")])
    parent_root = parent / hierarchy.VERSUM_DIRNAME
    distribution.publish(parent_root, "sink:norm:erased-shared")
    erasure.delete(parent_root, "sink:norm:erased-shared")  # erasure wins over publication

    idx = hierarchy.from_dimensioned_folder(child)
    assert "norm:erased-shared" not in _doc_ids(idx.search_similar("encrypt data at rest", k=5))
