"""Faithful-substring regression guard for claim ``text`` capture.

Before this fix, ``candidate_items`` hard-capped every claim's stored text at exactly
400 chars (``sentence[:400]``) regardless of where the real sentence ended. Real legal
provisions (enumerated lists in one grammatical sentence) run 1,000-7,000 chars, so the
cap: (1) chopped mid-word/mid-clause for long claims — an incomplete, non-self-contained
proposition wrongly treated as noise; (2) whenever char 400 happened to fall on an
internal period (an abbreviation, a sub-item number) the cut text ended in what LOOKED
like a real terminal period while the source actually continued past it with a comma —
a fabricated appearance of sentence-completeness, i.e. the stored text was no longer a
faithful substring of the source.

The fix (``_bounded_text``): below a generous pathological-case ceiling, text is
returned byte-for-byte unchanged — no cut, so no fabricated punctuation is possible.
Only over the ceiling is text cut, and only at a real word boundary, with an honest
ellipsis appended (never invented sentence-final punctuation).
"""
import versum.profiles  # noqa: F401 — register built-ins
from versum.io.extract import (
    CLAIM_TEXT_CEILING, _TRUNC_MARK, _bounded_text, candidate_items, segment_units,
)
from versum.profiles.law_eu import PROFILE as LAW

URN = "urn:t:span-truncation-test"


def _claims(text):
    units = segment_units(text)
    return [it for u in units for it in candidate_items(u, URN, LAW)]


# ── _bounded_text: direct unit coverage ────────────────────────────────────

def test_short_text_under_old_400_cap_is_byte_for_byte_unchanged():
    s = "The controller shall retain the record for five years."
    assert len(s) < 400
    assert _bounded_text(s) == s


def test_long_real_sentence_over_400_under_ceiling_captured_in_full():
    # a real, single grammatical sentence (comma-joined enumerated clauses) well over
    # the old 400-char cap but comfortably under the pathological ceiling
    clauses = ", ".join(f"category {i} of processing operations" for i in range(40))
    s = f"This Article applies to {clauses}, and to no other category."
    assert 400 < len(s) < CLAIM_TEXT_CEILING
    got = _bounded_text(s)
    assert got == s, "a real sentence under the ceiling must be captured whole"
    assert got.endswith("no other category."), "the true terminal period must survive"


def test_old_cap_would_have_fabricated_a_period_new_code_does_not():
    # construct so an internal ("abbreviation") period sits at exactly index 399 — the
    # old sentence[:400] slice would have stopped right there, making the truncated text
    # LOOK like a complete sentence ending in "." when the source actually continues
    # with a comma-joined clause and only its own, later, real period ends it.
    head = "A" * 395 + " Art."  # index 399 is the "." of "Art."
    assert len(head) == 400 and head[399] == "."
    tail = ", and shall further apply to subsequent enumerated categories as well."
    s = head + tail
    assert len(s) > 400

    # the bug, demonstrated: naive truncation fabricates a false full stop
    old_buggy_text = s[:400]
    assert old_buggy_text.endswith("."), "sanity: reproduces the reported failure mode"
    assert not s.startswith(old_buggy_text + "."), "the '.' at 400 is not the real end"

    # the fix: full faithful text, comma-continuation preserved, real end preserved
    got = _bounded_text(s)
    assert got == s
    assert ", and shall further apply" in got
    assert got.endswith("categories as well.")


def test_never_cuts_mid_word_and_never_appends_a_fabricated_period():
    # a single long clause with NO periods at all until far past the ceiling — the
    # pathological case the ceiling exists for (e.g. a malformed text layer where no
    # sentence-final period is ever found)
    words = [f"clause{i}" for i in range(3000)]
    s = " ".join(words)
    assert len(s) > CLAIM_TEXT_CEILING

    got = _bounded_text(s)
    assert got.endswith(_TRUNC_MARK), "over-ceiling text must carry the honest marker"
    body = got[: -len(_TRUNC_MARK)]
    assert not body.endswith("."), "must never invent terminal punctuation"
    assert s.startswith(body), "the kept text must be a faithful prefix of the source"
    # word-boundary proof: the source character right after the kept prefix is a space,
    # i.e. no word was sliced in half
    assert s[len(body)] == " ", "must cut at a real word boundary, never mid-word"
    assert len(body) <= CLAIM_TEXT_CEILING


def test_ceiling_cut_body_contains_no_partial_trailing_token():
    words = [f"tok{i}" for i in range(3000)]
    s = " ".join(words)
    got = _bounded_text(s)
    body = got[: -len(_TRUNC_MARK)]
    last_token = body.rsplit(" ", 1)[-1]
    # the last kept token must appear whole in the source at that exact position
    assert s[len(body) - len(last_token): len(body)] == last_token


# ── candidate_items: end-to-end wiring through the extractor ───────────────

def test_candidate_items_captures_long_real_clause_in_full_no_400_cut():
    clauses = "; ".join(f"point ({chr(97 + i)}) applies to category {i}" for i in range(30))
    text = f"The controller shall ensure that {clauses}; and that no data is retained beyond the stated period."
    items = _claims(text)
    assert items, "fixture must actually produce a candidate claim"
    long_items = [it for it in items if len(it["text"]) > 400]
    assert long_items, "fixture must exercise the >400-char path"
    for it in long_items:
        assert it["text"] in text, "stored text must be a faithful substring of the source"
        assert it["text"].endswith("stated period."), "must reach the real sentence end"


def test_candidate_items_short_sentence_unchanged_regression():
    text = "The processor shall notify the controller without undue delay."
    items = _claims(text)
    assert items
    for it in items:
        assert len(it["text"]) < 400
        assert it["text"] in text
