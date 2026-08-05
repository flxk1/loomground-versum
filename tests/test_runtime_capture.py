"""Runtime knowledge capture (``versum.capture``) — the source-less write door.

RVND needs to write NON-file runtime knowledge (a fact triple, a reasoning inference) into
the *same* dimensioned-subgraph sink used by file ingest, so it can retire its parallel store.
These tests prove that runtime captures:

  * lower to a VALID envelope (they round-trip through ``load_dimensioned_subgraphs``),
  * are idempotent on an identical re-append (sink receipt ``status="unchanged"``),
  * are searchable through the existing ``from_dimensioned_store`` read path (RVND pairs_search),
  * and flow through the WS-B sink capabilities — erasure hides a runtime node from search.

The sink contract and the file-ingest path are untouched; capture is purely additive.
"""
import pytest

from versum import append_fact, append_inference, fact_node_ids
from versum.capture import (
    RUNTIME_ASSERTION_DIGEST,
    RUNTIME_GROUNDING,
    RuntimeCaptureError,
    _digest,
)
from versum.ingestion import IdempotencyConflictError, load_dimensioned_subgraphs
from versum.store import erasure
from versum.store.retrieve import from_dimensioned_store


def _store(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    return root


# ── append_fact → valid, round-trips, idempotent ─────────────────────────────
def test_append_fact_lowers_to_two_nodes_one_relation(tmp_path):
    store = _store(tmp_path)
    receipt = append_fact(
        store, subject="Alice", predicate="located in", object="Berlin",
        dimension="geography", actor="rvnd-agent")
    assert receipt["status"] == "inserted"

    graphs = load_dimensioned_subgraphs(store)
    assert len(graphs) == 1
    graph = graphs[0]
    assert len(graph["nodes"]) == 2
    assert len(graph["relations"]) == 1

    relation = graph["relations"][0]
    # The declared dimension is the single nD axis and the relation's dimension.
    assert graph["nd"]["axes"] == ["geography"]
    assert relation["dimension"] == "geography"
    assert relation["relation_type"] == "located-in"      # predicate, slugged
    assert relation["properties"]["predicate"] == "located in"  # raw predicate kept

    # The synthetic runtime source/evidence conventions.
    assert graph["source"]["source_id"] == "runtime:rvnd-agent"
    assert graph["evidence"][0]["locator"].startswith("runtime:rvnd-agent:")
    # The subject sits at the object value along the declared axis.
    subject_id, object_id = fact_node_ids(subject="Alice", object="Berlin")
    by_id = {n["node_id"]: n for n in graph["nodes"]}
    assert by_id[subject_id]["dimensions"]["geography"] == "Berlin"
    assert set(by_id) == {subject_id, object_id}


def test_append_fact_is_idempotent(tmp_path):
    store = _store(tmp_path)
    first = append_fact(store, subject="Alice", predicate="located in", object="Berlin",
                        dimension="geography", actor="rvnd-agent")
    second = append_fact(store, subject="Alice", predicate="located in", object="Berlin",
                         dimension="geography", actor="rvnd-agent")
    assert first["status"] == "inserted"
    assert second["status"] == "unchanged"
    assert first["idempotency_key"] == second["idempotency_key"]
    assert len(load_dimensioned_subgraphs(store)) == 1


def test_same_triple_different_observed_at_is_a_conflict(tmp_path):
    """observed_at is NOT in the idempotency key, so re-appending the same triple with a
    different explicit timestamp is a genuine rebind the sink refuses (documented contract)."""
    store = _store(tmp_path)
    append_fact(store, subject="Alice", predicate="knows", object="Bob",
                dimension="social", actor="a", observed_at="2026-08-04T10:00:00Z")
    with pytest.raises(IdempotencyConflictError):
        append_fact(store, subject="Alice", predicate="knows", object="Bob",
                    dimension="social", actor="a", observed_at="2026-08-04T11:00:00Z")


# ── searchable through the existing read path (RVND pairs_search) ─────────────
def test_runtime_fact_is_searchable(tmp_path):
    store = _store(tmp_path)
    append_fact(store, subject="controller", predicate="must ensure", object="data protection",
                dimension="causal", actor="rvnd-agent")
    idx = from_dimensioned_store(store)
    hits = idx.search_similar("controller data protection", k=5)
    assert hits
    subject_id, _ = fact_node_ids(subject="controller", object="data protection")
    assert any(h["doc_id"] == subject_id for h in hits)
    # canonical_urn carries the synthetic runtime source id.
    assert hits[0]["canonical_urn"] == "runtime:rvnd-agent"


def test_unrelated_query_finds_nothing(tmp_path):
    store = _store(tmp_path)
    append_fact(store, subject="Alice", predicate="located in", object="Berlin",
                dimension="geography", actor="a")
    idx = from_dimensioned_store(store)
    assert idx.search_similar("wholly unrelated vocabulary", k=5) == []


# ── runtime knowledge is an EXPLICIT provenance class, not fake grounding ─────
def test_runtime_provenance_is_marked_and_not_self_referential(tmp_path):
    """Runtime knowledge is asserted-by-an-actor, not span-grounded: the envelope must SAY so
    (grounding markers) and must NOT manufacture grounding by hashing the assertion itself."""
    store = _store(tmp_path)
    append_fact(store, subject="Alice", predicate="located in", object="Berlin",
                dimension="geography", actor="rvnd-agent")
    graph = load_dimensioned_subgraphs(store)[0]

    # Every node and relation is stamped as a runtime provenance class, with the asserting
    # actor — a consumer can tell it apart from a span-grounded node.
    for node in graph["nodes"]:
        assert node["properties"]["grounding"] == RUNTIME_GROUNDING
        assert node["properties"]["actor"] == "rvnd-agent"
    for relation in graph["relations"]:
        assert relation["properties"]["grounding"] == RUNTIME_GROUNDING

    # The digest that the OLD, dishonest implementation used as both source and evidence
    # "grounding": a hash of the assertion itself.
    self_referential = _digest({
        "kind": "fact", "subject": "Alice", "predicate": "located in", "object": "Berlin",
        "dimension": "geography", "actor": "rvnd-agent"})

    # Source content_digest is the runtime source IDENTITY marker, never the assertion hash.
    assert graph["source"]["content_digest"].startswith("sha256:")
    assert graph["source"]["content_digest"] != self_referential

    # The single runtime evidence entry is an assertion RECORD (who/when), not a grounding
    # span: its content_digest is the fixed 'no grounded span' marker, not the assertion hash.
    runtime_evidence = graph["evidence"][0]
    assert runtime_evidence["content_digest"] == RUNTIME_ASSERTION_DIGEST
    assert runtime_evidence["content_digest"] != self_referential
    # source and evidence are distinct markers — grounding is not a single self-referential hash.
    assert graph["source"]["content_digest"] != runtime_evidence["content_digest"]


def test_capture_content_digest_hashes_the_capture_not_the_assertion(tmp_path):
    """An attached llm/web capture is provenance: its content_digest honestly hashes the
    capture content (real bytes), distinct from the runtime assertion marker."""
    store = _store(tmp_path)
    content = "Berlin is the capital of Germany."
    append_fact(store, subject="Berlin", predicate="capital of", object="Germany",
                dimension="geography", actor="rvnd-agent",
                captures=[{"kind": "llm_answer", "content": content}])
    graph = load_dimensioned_subgraphs(store)[0]
    capture = next(e for e in graph["evidence"] if e["evidence_id"].startswith("evidence:llm"))
    assert capture["content_digest"] == _digest(content)
    assert capture["content_digest"] != RUNTIME_ASSERTION_DIGEST


# ── append_inference → node/relation chain round-trip ────────────────────────
def test_append_inference_round_trips_as_chain(tmp_path):
    store = _store(tmp_path)
    receipt = append_inference(
        store,
        path=[
            {"subject": "Socrates", "predicate": "is a", "object": "man"},
            {"subject": "man", "predicate": "is", "object": "mortal"},
        ],
        dimension="logic", actor="reasoner")
    assert receipt["status"] == "inserted"

    graph = load_dimensioned_subgraphs(store)[0]
    # Three distinct terms (Socrates, man, mortal) → three nodes; two hops → two relations.
    assert len(graph["nodes"]) == 3
    assert len(graph["relations"]) == 2
    assert [r["dimension"] for r in graph["relations"]] == ["logic", "logic"]
    assert [r["relation_type"] for r in graph["relations"]] == ["is-a", "is"]

    # The chain is searchable and idempotent.
    idx = from_dimensioned_store(store)
    assert idx.search_similar("Socrates mortal", k=5)
    again = append_inference(
        store,
        path=[
            {"subject": "Socrates", "predicate": "is a", "object": "man"},
            {"subject": "man", "predicate": "is", "object": "mortal"},
        ],
        dimension="logic", actor="reasoner")
    assert again["status"] == "unchanged"


# ── erasure flows through the WS-B sink capabilities ─────────────────────────
def test_erasure_removes_runtime_node_from_search(tmp_path):
    store = _store(tmp_path)
    append_fact(store, subject="Alice", predicate="located in", object="Berlin",
                dimension="geography", actor="rvnd-agent")
    subject_id, _ = fact_node_ids(subject="Alice", object="Berlin")

    idx = from_dimensioned_store(store)
    assert any(h["doc_id"] == subject_id for h in idx.search_similar("Alice Berlin", k=5))

    # Address the runtime node through the sink erasure convention ("sink:" + raw node_id).
    erasure.delete(store, "sink:" + subject_id, reason="test", actor="rvnd-agent")

    idx = from_dimensioned_store(store)
    assert not any(h["doc_id"] == subject_id for h in idx.search_similar("Alice Berlin", k=5))


# ── llm / web evidence attaches as evidence, not as a first-class node ────────
def test_captures_attach_as_evidence(tmp_path):
    store = _store(tmp_path)
    append_fact(
        store, subject="Berlin", predicate="capital of", object="Germany",
        dimension="geography", actor="rvnd-agent",
        captures=[
            {"kind": "llm_answer", "content": "Berlin is the capital of Germany."},
            {"kind": "websearch", "content": "de.wikipedia.org/wiki/Berlin",
             "locator": "https://de.wikipedia.org/wiki/Berlin"},
        ])
    graph = load_dimensioned_subgraphs(store)[0]
    # Two captures + one synthetic runtime evidence, all bound to the runtime source.
    assert len(graph["evidence"]) == 3
    assert all(e["source_id"] == "runtime:rvnd-agent" for e in graph["evidence"])
    locators = [e["locator"] for e in graph["evidence"]]
    assert "https://de.wikipedia.org/wiki/Berlin" in locators
    # Captures are provenance, NOT extra knowledge nodes: still just the 2 fact nodes.
    assert len(graph["nodes"]) == 2
    # The relation references every evidence id (runtime + captures).
    assert len(graph["relations"][0]["evidence_ids"]) == 3


# ── input validation ─────────────────────────────────────────────────────────
def test_empty_terms_rejected(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(RuntimeCaptureError):
        append_fact(store, subject="", predicate="p", object="o",
                    dimension="d", actor="a")
    with pytest.raises(RuntimeCaptureError):
        append_inference(store, path=[], dimension="d", actor="a")
