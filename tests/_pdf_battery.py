"""Deterministic synthetic-PDF battery for the space-inference extractor (ADR-002).

Builds small PDFs that reproduce the real failure regimes (tight-merged, loose-tracked) plus
regression cases (normal prose, headings, single words, numbers, mixed sizes). Each builder
returns ``(pdf_path, expected_lines)`` so tests can assert word recovery AND no spurious
splitting. reportlab is a test-only dependency.
"""
from __future__ import annotations

from pathlib import Path


def _canvas(path):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    return canvas.Canvas(str(path), pagesize=A4)


def build_tight(dirpath) -> tuple:
    """Words drawn with a 1 pt inter-word gap (< default x_tolerance) → merges on default."""
    p = Path(dirpath) / "tight.pdf"
    c = _canvas(p); c.setFont("Helvetica", 11)
    lines = ["der Anspruch auf Herstellung des digitalen Produkts entsteht",
             "die Verordnung gilt fuer alle Anbieter und Betreiber"]
    y = 800
    for ln in lines:
        x = 60
        for w in ln.split():
            c.drawString(x, y, w)
            x += c.stringWidth(w, "Helvetica", 11) + 1.0
        y -= 26
    c.save()
    return str(p), lines


def build_tracked(dirpath) -> tuple:
    """Loose letter-tracking (charSpace) with real word spacing → shatters on a low global tol."""
    p = Path(dirpath) / "tracked.pdf"
    c = _canvas(p)
    lines = ["Verhaeltnismaessigkeit und Bestimmtheit", "Grundrechte gelten unmittelbar"]
    y = 800
    for cs, ln in zip((1.0, 2.0), lines):
        to = c.beginText(60, y); to.setFont("Helvetica", 11); to.setCharSpace(cs)
        to.textLine(ln); c.drawText(to); y -= 28
    c.save()
    return str(p), lines


def build_normal(dirpath) -> tuple:
    """Ordinary prose with real space glyphs → must pass through unchanged."""
    p = Path(dirpath) / "normal.pdf"
    c = _canvas(p); c.setFont("Helvetica", 11)
    lines = ["Ein normaler Satz mit echten Leerzeichen bleibt heil.",
             "The controller shall ensure an appropriate level of protection."]
    y = 800
    for ln in lines:
        c.drawString(60, y, ln); y -= 26
    c.save()
    return str(p), lines


def build_heading(dirpath) -> tuple:
    """Large-font heading with real spaces → a low absolute threshold would split it."""
    p = Path(dirpath) / "heading.pdf"
    c = _canvas(p)
    c.setFont("Helvetica-Bold", 22); c.drawString(60, 800, "Grosse Ueberschrift Mit Woertern")
    c.setFont("Helvetica", 11); c.drawString(60, 760, "danach folgt der laufende Text hier")
    c.save()
    return str(p), ["Grosse Ueberschrift Mit Woertern", "danach folgt der laufende Text hier"]


def build_single_and_numeric(dirpath) -> tuple:
    """A single long word (no break) and a numeric line → no spurious splits."""
    p = Path(dirpath) / "edge.pdf"
    c = _canvas(p); c.setFont("Helvetica", 11)
    c.drawString(60, 800, "Unverhaeltnismaessigkeit")
    c.drawString(60, 770, "12345 67890 100,00 EUR 2024")
    c.save()
    return str(p), ["Unverhaeltnismaessigkeit", "12345 67890 100,00 EUR 2024"]


def _draw_words(c, words, gaps, font, size, x, y):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    xx = x
    for i, w in enumerate(words):
        if i > 0:
            xx += gaps[i - 1]
        c.drawString(xx, y, w)
        xx += stringWidth(w, font, size)


def build_uneven_gaps(dirpath) -> tuple:
    """Uneven word gaps on one line (wider gap after a period; a justification-stretched gap):
    every word boundary must still split, not only the widest one. Regression for the
    largest-single-jump defeat found by adversarial review."""
    p = Path(dirpath) / "uneven.pdf"
    c = _canvas(p); c.setFont("Times-Roman", 12)
    _draw_words(c, ["Anspruch", "besteht.", "Der", "Schuldner", "haftet"],
                [2.0, 4.5, 2.0, 2.0], "Times-Roman", 12, 72, 700)
    _draw_words(c, ["der", "Anspruch", "auf", "Herstellung", "des", "Werkes"],
                [2.2, 2.2, 2.2, 9.0, 2.2], "Times-Roman", 12, 72, 670)
    c.save()
    return str(p), ["Anspruch besteht. Der Schuldner haftet",
                    "der Anspruch auf Herstellung des Werkes"]


def build_table(dirpath) -> tuple:
    """Prose above and below a ruled 3x3 table whose cells are schema-noise words.
    Returns (path, prose_lines, cell_words): the extractor must keep the prose and,
    with skip_tables, drop every cell word."""
    p = Path(dirpath) / "table.pdf"
    c = _canvas(p); c.setFont("Helvetica", 11)
    prose = ["die Verordnung gilt unmittelbar in jedem Mitgliedstaat",
             "die Grundrechte gelten ebenso unmittelbar"]
    c.drawString(60, 800, prose[0])
    xs, ys = [60, 180, 300, 420], [700, 730, 760]
    c.grid(xs, ys)
    cells = [["Feld", "Typ", "Format"], ["Datum", "date", "YYYY"]]
    for r, row in enumerate(cells):
        for col, val in enumerate(row):
            c.drawString(xs[col] + 6, ys[len(ys) - 2 - r] + 10, val)
    c.drawString(60, 640, prose[1])
    c.save()
    return str(p), prose, [w for row in cells for w in row]


ALL_BUILDERS = [build_tight, build_tracked, build_normal, build_heading,
                build_single_and_numeric, build_uneven_gaps]
