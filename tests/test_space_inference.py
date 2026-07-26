"""Adaptive space inference (ADR-002): merged words are recovered, clean text is untouched.

Uses a synthetic-PDF battery reproducing the real failure regimes. reportlab is required for
these tests; they skip if it is unavailable.
"""
import pytest

pytest.importorskip("reportlab")
pytest.importorskip("pdfplumber")

from versum.io import extract as ex       # noqa: E402
from tests import _pdf_battery as bat      # noqa: E402


def _lines(text):
    return [l for l in text.splitlines() if l.strip()]


def test_tight_merged_words_are_recovered(tmp_path):
    path, expected = bat.build_tight(tmp_path)
    got = _lines(ex.extract_text(path))
    assert got == expected, got


def test_loose_tracked_words_are_not_shattered(tmp_path):
    path, expected = bat.build_tracked(tmp_path)
    got = _lines(ex.extract_text(path))
    assert got == expected, got


def test_normal_prose_is_unchanged(tmp_path):
    path, expected = bat.build_normal(tmp_path)
    got = _lines(ex.extract_text(path))
    assert got == expected, got


def test_heading_and_body_mixed_sizes(tmp_path):
    path, expected = bat.build_heading(tmp_path)
    got = _lines(ex.extract_text(path))
    assert got == expected, got


def test_single_word_and_numbers_no_spurious_splits(tmp_path):
    path, expected = bat.build_single_and_numeric(tmp_path)
    got = _lines(ex.extract_text(path))
    assert got == expected, got


def test_uneven_word_gaps_all_split(tmp_path):
    # regression: a wider gap after a period / a justification-stretched gap must not cause the
    # narrower genuine word gaps to merge (adversarial finding).
    path, expected = bat.build_uneven_gaps(tmp_path)
    got = _lines(ex.extract_text(path))
    assert got == expected, got


def _draw(c, words, gaps, font, size, x, y):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    xx = x
    for i, w in enumerate(words):
        if i > 0:
            xx += gaps[i - 1]
        c.setFont(font, size[i] if isinstance(size, list) else size)
        c.drawString(xx, y, w)
        xx += stringWidth(w, font, size[i] if isinstance(size, list) else size)


def test_two_column_row_within_cell_words_split(tmp_path):
    # adversarial finding: a table/two-column row has a huge inter-cell gap; within-cell words
    # must still split (not glue) even though the inter-cell gap dominates the line.
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    p = str(tmp_path / "cols.pdf")
    c = canvas.Canvas(p, pagesize=letter)
    # left cell "Anspruch auf Herstellung", ~180pt gap, right cell "Betrag in Euro"
    _draw(c, ["Anspruch", "auf", "Herstellung"], [2.0, 2.0], "Helvetica", 11, 72, 700)
    _draw(c, ["Betrag", "in", "Euro"], [2.0, 2.0], "Helvetica", 11, 320, 700)
    c.save()
    got = _lines(ex.extract_text(p))
    assert got == ["Anspruch auf Herstellung Betrag in Euro"], got


def test_mixed_font_sizes_on_line_do_not_merge_neighbours(tmp_path):
    # adversarial finding: an outlier-size word in the middle must not cause the flanking
    # small-font words to merge.
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    p = str(tmp_path / "sizes.pdf")
    c = canvas.Canvas(p, pagesize=letter)
    _draw(c, ["one", "two", "HUGE", "three", "four"], [2.0, 2.0, 2.0, 2.0],
          "Helvetica", [8, 8, 28, 8, 8], 72, 700)
    c.save()
    got = " ".join(_lines(ex.extract_text(p))).split()
    assert got == ["HUGE", "one", "two", "three", "four"] or got == ["one", "two", "HUGE", "three", "four"], got


def test_short_numeric_reference_line_splits(tmp_path):
    # regression: a short merged line of number/short tokens ("5 zu 3", scores, references)
    # must split at its genuine word gaps — an earlier majority-split guard wrongly merged it.
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase.pdfmetrics import stringWidth
    p = str(tmp_path / "score.pdf")
    c = canvas.Canvas(p); c.setFont("Helvetica", 10); x = 72
    for t in ["5", "zu", "3"]:
        c.drawString(x, 700, t); x += stringWidth(t, "Helvetica", 10) + 2.0
    c.showPage(); c.save()
    assert _lines(ex.extract_text(p)) == ["5 zu 3"], ex.extract_text(p)


def test_uniformly_spaced_line_is_not_shattered(tmp_path):
    # a fully letter-spaced line (Sperrsatz heading / spaced initials) must NOT be shattered
    # into single letters; the majority-split guard leaves it as one token (correct recovery
    # for Sperrsatz, and identical to the pre-fix behaviour for digit rows).
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase.pdfmetrics import stringWidth
    p = str(tmp_path / "sperr.pdf")
    c = canvas.Canvas(p); c.setFont("Helvetica", 11); x = 72
    for ch in "GRUNDRECHTE":
        c.drawString(x, 700, ch); x += stringWidth(ch, "Helvetica", 11) + 2.5
    c.showPage(); c.save()
    out = " ".join(_lines(ex.extract_text(p)))
    assert " ".join(list("GRUNDRECHTE")) not in out, out   # not shattered to single letters


def test_extraction_is_deterministic(tmp_path):
    path, _ = bat.build_tight(tmp_path)
    assert ex.extract_text(path) == ex.extract_text(path)


def test_no_merged_glob_tokens_remain(tmp_path):
    # after repair, no absurd run-together token should survive on the merged fixtures
    for build in (bat.build_tight, bat.build_tracked):
        path, _ = build(tmp_path)
        for tok in ex.extract_text(path).split():
            assert len(tok) <= 30, f"glob token survived: {tok!r}"
