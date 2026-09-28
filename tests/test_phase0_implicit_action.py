"""Phase 0 ontology seam, item (4): a norm with no extractable action span abstains
(reason code ``ACTION_IMPLICIT``) instead of being silently skipped or fabricating a
placeholder entry, and the "every deontic action resolves through embeds" invariant
applies only to non-abstained rows.

Uses two small FAKE plane descriptors (never a real plane, never edited src) so the two
branches -- "resolves cleanly" and "abstains" -- are each provoked deterministically:

  * ``fakenorm`` publishes a ``bearer`` axis (so :func:`versum.planes.build_source_entries`
    treats its claims as norms whose content should be lowered through the factual
    plane) and, per sentence, EITHER a valid ``spans.content`` sub-span (resolves) OR no
    ``spans`` at all (abstains -- no extractable action span, i.e. "the bank" sentence
    below names no verb-shaped action).
  * ``fakefactual`` is registered under the real plane id ``"factual"`` (the one
    :func:`build_source_entries` looks for by id) so the lowering path is reachable at
    all; its own claims are trivial and asserted (``asserted`` defaults True elsewhere,
    irrelevant here since the abstaining branch never calls it).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from versum import planes as pl


# ── fake planes ──────────────────────────────────────────────────────
def _fake_norm_system() -> dict:
    return {
        "id": "fakenorm-system", "namespace": "fakenorm.test", "version": "0.0.1-test",
        "axes": {"bearer": {"value_type": "string", "vocabulary_mode": "open",
                            "cardinality": "one"}},
        "bindings": [], "validation": {"unknown_values": "reject"},
    }


def _fake_norm_produce(sentence: str, context: dict | None = None) -> list[dict]:
    """Every sentence names a bearer ('it'); a sentence containing 'act' also publishes a
    valid spans.content sub-span (resolves); one that does not (e.g. names a bearer but
    no verb-shaped action) publishes no spans at all (abstains: ACTION_IMPLICIT)."""
    claims = []
    if "act" in sentence:
        i = sentence.index("act")
        content = {"start": i, "end": i + len("act"), "text": "act"}
        claims.append({"relation": "norm", "span": [0, len(sentence)],
                       "coordinates": {"bearer": "it"}, "slots": {},
                       "spans": {"content": content}, "method": "fake-rule"})
    else:
        claims.append({"relation": "norm", "span": [0, len(sentence)],
                       "coordinates": {"bearer": "it"}, "slots": {}, "method": "fake-rule"})
    return claims


def _fake_norm_descriptor() -> dict:
    return {
        "plane": "fakenorm", "language_version": "0.0.1-test",
        "nd_system": _fake_norm_system(), "binding": {}, "produce": _fake_norm_produce,
        "examples": [],
    }


def _fake_factual_system() -> dict:
    return {
        "id": "fakefactual-system", "namespace": "fakefactual.test", "version": "0.0.1-test",
        "axes": {"subject": {"value_type": "string", "vocabulary_mode": "open",
                             "cardinality": "one"},
                "predicate": {"value_type": "string", "vocabulary_mode": "open",
                             "cardinality": "one"},
                "object": {"value_type": "string", "vocabulary_mode": "open",
                          "cardinality": "one"}},
        "bindings": [], "validation": {"unknown_values": "reject"},
    }


def _fake_factual_produce(sentence: str, context: dict | None = None) -> list[dict]:
    subject = (context or {}).get("subject", "")
    return [{"relation": "is", "span": [0, len(sentence)],
            "coordinates": {"subject": subject, "predicate": "is", "object": "x"},
            "slots": {}, "method": "fake-rule"}]


def _fake_factual_descriptor() -> dict:
    return {
        "plane": "factual", "language_version": "0.0.1-test",
        "nd_system": _fake_factual_system(), "binding": {}, "produce": _fake_factual_produce,
        "examples": [],
    }


def _planes() -> list:
    return pl.load_planes([_fake_norm_descriptor(), _fake_factual_descriptor()])


# ── the abstaining branch ────────────────────────────────────────────
def test_a_norm_with_no_extractable_action_span_abstains():
    text = "It fixes nothing at all."
    out = pl.build_source_entries(text, "urn:test:abstain", _planes())
    assert len(out.abstentions) == 1
    (record,) = out.abstentions
    assert record["reason"] == pl.ACTION_IMPLICIT
    assert record["source_urn"] == "urn:test:abstain"
    assert record["detail"]


def test_an_abstained_norm_creates_no_placeholder_entry():
    text = "It fixes nothing at all."
    out = pl.build_source_entries(text, "urn:test:abstain", _planes())
    (norm_entry_id,) = {r["entry_id"] for r in out.abstentions}
    # the only entries this run produces are the sentence entry itself -- no embedded
    # "action" / content sub-entry is ever fabricated for the abstained claim.
    assert len(out.entries) == 1
    (sentence_entry,) = out.entries
    assert sentence_entry["entry_kind"] == "sentence"
    assert sentence_entry["item_id"] == norm_entry_id
    assert not out.links, "an abstained norm must produce no structural embeds link"


def test_abstention_id_is_deterministic_across_reindexing():
    text = "It fixes nothing at all."
    out1 = pl.build_source_entries(text, "urn:test:abstain", _planes())
    out2 = pl.build_source_entries(text, "urn:test:abstain", _planes())
    assert out1.abstentions == out2.abstentions


# ── the resolving branch ─────────────────────────────────────────────
def test_a_norm_with_an_extractable_action_span_resolves_and_does_not_abstain():
    text = "It shall act now."
    out = pl.build_source_entries(text, "urn:test:resolve", _planes())
    assert out.abstentions == []
    assert len(out.entries) == 2  # the sentence + its content entry
    content = [e for e in out.entries if e["entry_kind"] == "embedded"]
    assert len(content) == 1 and content[0]["text"] == "act"
    embeds = [l for l in out.links if l["relation"] == pl.EMBED_LINK_RELATION]
    assert len(embeds) == 1


# ── "every deontic action resolves through embeds" — non-abstained rows only ──
def _write_minimal_store(tmp_path: Path, out) -> Path:
    d = tmp_path / ".versum"
    d.mkdir()
    claims_jsonl = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in out.claims)
    (d / "entry_claims.jsonl").write_text(claims_jsonl, encoding="utf-8")
    import csv
    with open(d / "entry_links.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=pl.LINK_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in out.links:
            w.writerow(row)
    abst_jsonl = "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in out.abstentions)
    (d / "abstentions.jsonl").write_text(abst_jsonl, encoding="utf-8")
    return d


def test_invariant_holds_when_the_only_bearer_row_is_abstained(tmp_path):
    out = pl.build_source_entries("It fixes nothing at all.", "urn:test:abstain",
                                  _planes())
    store = _write_minimal_store(tmp_path, out)
    assert pl.check_action_embeds_invariant(store) == []


def test_invariant_holds_when_the_bearer_row_resolves_through_embeds(tmp_path):
    out = pl.build_source_entries("It shall act now.", "urn:test:resolve", _planes())
    store = _write_minimal_store(tmp_path, out)
    assert pl.check_action_embeds_invariant(store) == []


def test_invariant_violation_is_reported_for_a_bearer_row_neither_embedded_nor_abstained(
        tmp_path):
    """A real (not abstained, not embedded) violation IS caught -- proves the invariant
    checker is not vacuously true. Built by hand (never in-tree): an entry_claims.jsonl
    record naming a bearer with no matching embeds link and no abstention record."""
    d = tmp_path / ".versum"
    d.mkdir()
    fake_claim_record = {"item_id": "ent-fakebearer0000", "plane": "fakenorm",
                         "claim": {"coordinates": {"bearer": "it"}}}
    (d / "entry_claims.jsonl").write_text(
        json.dumps(fake_claim_record, ensure_ascii=False) + "\n", encoding="utf-8")
    (d / "entry_links.csv").write_text(",".join(pl.LINK_COLUMNS) + "\n", encoding="utf-8")
    (d / "abstentions.jsonl").write_text("", encoding="utf-8")
    violations = pl.check_action_embeds_invariant(d)
    assert len(violations) == 1
    assert "ent-fakebearer0000" in violations[0]


# ── mutation harness note ───────────────────────────────────────────
# The implicit-action mutation run (fabricating a placeholder content entry for an
# abstained norm on a scratch copy of this repo, never in-tree) and its failing node id
# are reported by the calling task, not executed as part of the committed suite -- see the
# task report.
