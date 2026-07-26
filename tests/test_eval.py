"""Unit tests for the domain-general metric harness (versum/eval.py).

No domain data here: every gold set is a synthetic literal or a temp file.
"""
from versum.eval import score, mint_curve, load_gold


def test_score_hand_values():
    gold = {"a", "b", "c", "d"}
    found = {"a", "b", "x"}  # tp=2 (a,b), fp=1 (x), fn=2 (c,d)
    r = score(found, gold)
    assert r["tp"] == 2 and r["fp"] == 1 and r["fn"] == 2
    assert r["precision"] == 2 / 3
    assert r["recall"] == 2 / 4
    assert abs(r["f1"] - (2 * (2 / 3) * 0.5) / ((2 / 3) + 0.5)) < 1e-9


def test_score_perfect_and_empty():
    gold = {"a", "b"}
    assert score({"a", "b"}, gold) == {
        "precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 2, "fp": 0, "fn": 0}
    empty = score(set(), gold)
    assert empty["precision"] == 0.0 and empty["recall"] == 0.0 and empty["f1"] == 0.0
    assert empty["fn"] == 2


def test_mint_curve_convergence():
    docs = [
        {"a", "b", "c"},       # doc1: all 3 new
        {"b", "c", "d"},       # doc2: only d new
        {"a", "b", "c", "d"},  # doc3: nothing new
        {"e"},                 # doc4: 1 new
    ]
    assert mint_curve(docs) == [3, 1, 0, 1]


def test_mint_curve_empty():
    assert mint_curve([]) == []


def test_load_gold(tmp_path):
    p = tmp_path / "gold.txt"
    p.write_text("# a comment\nalpha\nbeta\n\n  gamma  \n", encoding="utf-8")
    assert load_gold(p) == {"alpha", "beta", "gamma"}
