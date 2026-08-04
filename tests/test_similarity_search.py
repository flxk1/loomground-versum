"""Keyword-overlap (Jaccard) search: ranking, k limit, empty store, recency tie-break,
string-vs-dict query, facet-value contribution, and scoping via facet filters."""
from versum.store.retrieve import Doc, SearchIndex, query_tokens


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


def test_ranks_by_keyword_overlap():
    idx = SearchIndex(_docs())
    hits = idx.search_similar("controller protection data", k=5)
    assert hits and hits[0]["doc_id"] == "claim:1"
    # every hit shares at least one token, so scores are strictly positive and descending
    scores = [h["score"] for h in hits]
    assert all(s > 0 for s in scores) and scores == sorted(scores, reverse=True)


def test_k_limits_result_count():
    idx = SearchIndex(_docs())
    assert len(idx.search_similar("data controller provider consent", k=1)) == 1
    assert len(idx.search_similar("data controller provider consent", k=2)) == 2


def test_empty_store_returns_nothing():
    assert SearchIndex([]).search_similar("controller data", k=5) == []


def test_no_overlap_returns_nothing():
    idx = SearchIndex(_docs())
    assert idx.search_similar("wholly unrelated vocabulary", k=5) == []


def test_tie_break_by_recency():
    # identical token bags → identical Jaccard; the more-recent doc must sort first.
    docs = [
        Doc("claim:old", "claim", "controller must protect data",
            facets={"type": "claim"}, recency=1.0),
        Doc("claim:new", "claim", "controller must protect data",
            facets={"type": "claim"}, recency=2.0),
    ]
    hits = SearchIndex(docs).search_similar("controller protect data", k=5)
    assert [h["doc_id"] for h in hits] == ["claim:new", "claim:old"]
    assert hits[0]["score"] == hits[1]["score"]


def test_string_and_dict_query_agree():
    idx = SearchIndex(_docs())
    as_string = idx.search_similar("controller protection data", k=5)
    as_dict = idx.search_similar({"summary": "controller protection data"}, k=5)
    assert as_string == as_dict


def test_dict_query_keywords_and_facets_contribute():
    idx = SearchIndex(_docs())
    # 'consent' appears only in claim:2; supplying it via keywords/facets surfaces it.
    by_keywords = idx.search_similar({"summary": "", "keywords": ["consent"]}, k=5)
    by_facets = idx.search_similar({"summary": "", "facets": {"note": "consent"}}, k=5)
    assert by_keywords and by_keywords[0]["doc_id"] == "claim:2"
    assert [h["doc_id"] for h in by_keywords] == [h["doc_id"] for h in by_facets]


def test_facet_filter_scopes_candidates():
    idx = SearchIndex(_docs())
    hits = idx.search_similar("controller data provider", filters={"domain": "ai"}, k=5)
    assert {h["doc_id"] for h in hits} <= {"claim:3"}


def test_query_tokens_string_vs_dict_equal():
    assert query_tokens("controller data") == query_tokens(
        {"summary": "controller data", "facets": {}})
    assert query_tokens({"summary": "a", "keywords": ["controller"]}) == {"controller"}


def test_determinism_same_results():
    idx = SearchIndex(_docs())
    assert idx.search_similar("data consent controller", k=5) == \
        idx.search_similar("data consent controller", k=5)
