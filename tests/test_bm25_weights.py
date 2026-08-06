# SPDX-License-Identifier: Apache-2.0
"""BM25.score weighted-query support (backward-compatible)."""
from versum.store.retrieve import BM25, tokenize

_DOCS = [
    tokenize("the controller must erase personal data on request"),
    tokenize("erasure right of the data subject under article seventeen"),
    tokenize("unrelated text about weather and traffic"),
]


def test_weights_none_is_the_historical_unweighted_score():
    bm = BM25().fit(_DOCS)
    q = ["erase", "data"]
    for i in range(len(_DOCS)):
        assert bm.score(q, i) == bm.score(q, i, weights=None)


def test_weights_down_weight_expanded_terms():
    bm = BM25().fit(_DOCS)
    q = ["erase", "erasure"]  # treat 'erasure' as an expanded synonym at 0.5
    full = bm.score(q, 1)                                   # both full weight
    weighted = bm.score(q, 1, weights={"erasure": 0.5})     # expanded discounted
    assert weighted < full  # the discount lowers the contribution of 'erasure'
    # a term absent from the weights map keeps weight 1.0
    assert bm.score(q, 1, weights={"nonexistent": 0.1}) == full
