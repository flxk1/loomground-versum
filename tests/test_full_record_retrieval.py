"""Full-record retrieval (``get_record`` / ``search_records``) over the sink store.

``search_similar`` / ``from_dimensioned_store`` return *lossy* hits — ``doc_id``, ``score``,
``snippet[:200]`` — which is enough to rank but not to reconstruct a knowledge item. RVND is
retiring its parallel knowledge store (``memory.py``) and must read the WHOLE record back from
the versum sink: the node (type + dimensions + all properties), every relation touching it
(both directions), and the transaction's ``source`` / ``evidence`` provenance. It then applies
its OWN enforcement (redaction, lock/seal, source scoping) over that record — versum returns
the full record and does NOT redact or lock. These tests pin that contract.
"""
from versum import append_fact, fact_node_ids, get_record, search_records
from versum.store import erasure
from versum.store.retrieve import from_dimensioned_store


def _store(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    return root


# ── get_record returns the full record: node + relation + provenance ──────────
def test_get_record_returns_node_relation_and_provenance(tmp_path):
    store = _store(tmp_path)
    append_fact(store, subject="controller", predicate="must ensure",
                object="data protection", dimension="causal", actor="rvnd-agent")
    subject_id, object_id = fact_node_ids(subject="controller", object="data protection")

    record = get_record(store, subject_id)
    assert record is not None
    # The node itself — type, dimensions and ALL properties (not a 200-char snippet).
    assert record["node_id"] == subject_id
    assert record["node_type"] == "entity"
    assert record["dimensions"]["causal"] == "data protection"
    assert record["properties"]["statement"] == "controller must ensure data protection"
    assert record["properties"]["kind"] == "runtime-fact"

    # Every relation touching the node (both directions). The subject is the source end.
    assert len(record["relations"]) == 1
    relation = record["relations"][0]
    assert relation["relation_type"] == "must-ensure"
    assert relation["properties"]["predicate"] == "must ensure"
    assert relation["source"]["value"] == subject_id
    assert relation["target"]["value"] == object_id

    # The transaction's source/evidence provenance — the synthetic runtime source.
    assert record["source"]["source_id"] == "runtime:rvnd-agent"
    assert record["source"]["content_digest"].startswith("sha256:")
    assert record["evidence"]
    assert record["evidence"][0]["locator"].startswith("runtime:rvnd-agent:")
    assert record["evidence"][0]["source_id"] == "runtime:rvnd-agent"


def test_get_record_finds_relation_from_the_target_side(tmp_path):
    """'both directions': the object node's record carries the same relation (target end)."""
    store = _store(tmp_path)
    append_fact(store, subject="controller", predicate="must ensure",
                object="data protection", dimension="causal", actor="rvnd-agent")
    subject_id, object_id = fact_node_ids(subject="controller", object="data protection")

    record = get_record(store, object_id)
    assert record is not None
    assert len(record["relations"]) == 1
    assert record["relations"][0]["target"]["value"] == object_id
    assert record["relations"][0]["source"]["value"] == subject_id


# ── search_records carries the FULL record + score, not a snippet ─────────────
def test_search_records_carries_full_record_and_score(tmp_path):
    store = _store(tmp_path)
    append_fact(store, subject="controller", predicate="must ensure",
                object="data protection", dimension="causal", actor="rvnd-agent")
    subject_id, _ = fact_node_ids(subject="controller", object="data protection")

    hits = search_records(store, "controller data protection", k=5)
    assert hits
    hit = next(h for h in hits if h["node_id"] == subject_id)
    # A hit is the full record shape (NOT a snippet) plus a score.
    assert "snippet" not in hit
    assert set(hit) == {"node_id", "node_type", "dimensions", "properties",
                        "source", "evidence", "relations", "score"}
    assert hit["score"] > 0
    assert hit["properties"]["statement"] == "controller must ensure data protection"
    assert hit["source"]["source_id"] == "runtime:rvnd-agent"
    assert hit["relations"] and hit["relations"][0]["relation_type"] == "must-ensure"

    # search_similar remains untouched (back-compat): it still returns lossy snippet hits.
    lossy = from_dimensioned_store(store).search_similar("controller data protection", k=5)
    assert lossy and "snippet" in lossy[0] and "relations" not in lossy[0]


# ── erasure: an erased node is None and absent from search_records ────────────
def test_erased_node_is_absent_from_get_and_search(tmp_path):
    store = _store(tmp_path)
    append_fact(store, subject="Alice", predicate="located in", object="Berlin",
                dimension="geography", actor="rvnd-agent")
    subject_id, _ = fact_node_ids(subject="Alice", object="Berlin")

    assert get_record(store, subject_id) is not None
    assert any(h["node_id"] == subject_id
               for h in search_records(store, "Alice Berlin", k=5))

    # Erase through the sink convention ("sink:" + raw node_id).
    erasure.delete(store, "sink:" + subject_id, reason="test", actor="rvnd-agent")

    assert get_record(store, subject_id) is None
    assert not any(h["node_id"] == subject_id
                   for h in search_records(store, "Alice Berlin", k=5))


# ── unknown id → None ─────────────────────────────────────────────────────────
def test_get_record_unknown_id_returns_none(tmp_path):
    store = _store(tmp_path)
    append_fact(store, subject="Alice", predicate="located in", object="Berlin",
                dimension="geography", actor="rvnd-agent")
    assert get_record(store, "entity:does-not-exist:0000000000") is None


def test_get_record_on_empty_store_returns_none(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert get_record(empty, "entity:anything:0000000000") is None
    assert search_records(empty, "anything", k=5) == []
