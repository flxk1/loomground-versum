"""Hybrid retrieval (ADR-004): facet precision, BM25 ranking, dense fusion, determinism."""
from versum.store.retrieve import (Doc, SearchIndex, BM25, HashingDense, NullDense,
                             tokenize, docs_from_kg)


def _docs():
    return [
        Doc("claim:1", "claim", "the controller must ensure protection of personal data",
            facets={"type": "claim", "predicate": "imposes", "domain": "privacy"},
            domain="privacy", canonical_urn="urn:a"),
        Doc("claim:2", "claim", "the processor may transfer data with consent",
            facets={"type": "claim", "predicate": "permits", "domain": "privacy"},
            domain="privacy", canonical_urn="urn:b"),
        Doc("claim:3", "claim", "the provider shall register the high risk system",
            facets={"type": "claim", "predicate": "imposes", "domain": "ai"},
            domain="ai", canonical_urn="urn:c"),
        Doc("concept:m-d-imposes-controller", "concept", "controller — imposes (is)",
            facets={"type": "concept", "predicate": "imposes"},
            concept_id="m-d-imposes-controller"),
    ]


def test_bm25_ranks_query_term_docs_first():
    idx = SearchIndex(_docs())
    hits = idx.search("controller protection", k=5)
    assert hits and hits[0]["doc_id"] == "claim:1"


def test_facet_filter_is_exact():
    idx = SearchIndex(_docs())
    hits = idx.search("", filters={"predicate": "permits"}, k=10)
    assert [h["doc_id"] for h in hits] == ["claim:2"]


def test_facet_and_query_combine():
    idx = SearchIndex(_docs())
    hits = idx.search("data", filters={"domain": "privacy", "type": "claim"}, k=10)
    ids = {h["doc_id"] for h in hits}
    assert ids <= {"claim:1", "claim:2"} and "claim:3" not in ids


def test_type_facet_selects_concepts():
    idx = SearchIndex(_docs())
    hits = idx.search("controller", filters={"type": "concept"}, k=10)
    assert hits and hits[0]["type"] == "concept"


def test_determinism_same_results():
    idx = SearchIndex(_docs())
    assert idx.search("data consent", k=5) == idx.search("data consent", k=5)


def test_dense_rerank_path_runs_and_is_deterministic():
    a = SearchIndex(_docs(), dense=HashingDense()).search("controller data", k=5)
    b = SearchIndex(_docs(), dense=HashingDense()).search("controller data", k=5)
    assert a == b and a                      # fusion path runs, stable across instances


def test_null_dense_is_default_no_crash():
    idx = SearchIndex(_docs(), dense=NullDense())
    assert idx.search("controller", k=3)


def test_bm25_idf_prefers_rare_terms():
    bm = BM25().fit([["a", "b"], ["a", "c"], ["a", "d"]])
    # 'a' appears in all docs → idf ~0; a rare term scores higher
    assert bm.idf["b"] > bm.idf["a"]


def test_tokenize_drops_short_and_punct():
    assert tokenize("The, EU-AI Act 2024!") == ["the", "eu", "ai", "act", "2024"]


def test_docs_from_kg_reads_store(tmp_path):
    import csv, json
    bd = tmp_path / "by-domain" / "privacy"
    bd.mkdir(parents=True)
    with open(bd / "claims.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["canonical_urn", "library", "item_id", "text",
                                           "polarity", "predicate", "modality", "quantification"])
        w.writeheader()
        w.writerow({"canonical_urn": "urn:a", "library": "L", "item_id": "i1",
                    "text": "controller must protect data", "polarity": "D",
                    "predicate": "imposes", "modality": "obliged", "quantification": "null"})
    (tmp_path / "canon.json").write_text(json.dumps(
        {"concepts": [{"concept_id": "m-d-imposes-controller", "label": "controller — imposes",
                       "predicate": "imposes", "domains": ["privacy"], "m": 1}]}))
    docs = docs_from_kg(tmp_path)
    assert any(d.type == "claim" for d in docs) and any(d.type == "concept" for d in docs)
    idx = SearchIndex(docs)
    assert idx.search("controller", filters={"predicate": "imposes"}, k=5)


def test_persisted_index_roundtrip_preserves_results(tmp_path):
    idx = SearchIndex(_docs())
    before = idx.search("controller data", filters={"domain": "privacy"}, k=5)
    path = tmp_path / "search-index.json"
    idx.save(path)
    restored = SearchIndex.load(path)
    assert restored.search("controller data", filters={"domain": "privacy"}, k=5) == before


def test_incremental_update_adds_replaces_and_removes():
    idx = SearchIndex(_docs()[:2])
    replacement = Doc("claim:1", "claim", "replacement rareword",
                      facets={"type": "claim", "domain": "privacy"})
    addition = Doc("claim:9", "claim", "new material",
                   facets={"type": "claim", "domain": "new"})
    stats = idx.update([replacement, addition], remove_ids=("claim:2",))
    assert stats == {"added": 1, "replaced": 1, "removed": 1, "total": 2}
    assert idx.search("rareword")[0]["doc_id"] == "claim:1"
    assert idx.search("", filters={"domain": "new"})[0]["doc_id"] == "claim:9"
