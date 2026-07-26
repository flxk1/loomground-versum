"""Profile-parameterized claim extractor — the candidate claim-layer substrate.

Deterministic, no LLM. Given a PDF already in the graph and its source URN plus an
active ``Profile``, this:

  1. extracts text (pdfplumber),
  2. segments it into units — articles, recitals or paragraphs — with char spans,
  3. scans each unit for the profile's surface markers and emits **candidate** claim
     items stamped on the closed-vocabulary axes (predicate / modality /
     quantification), each anchored to a char span and to the source URN.

All vocabulary comes from the ``Profile`` — this module hardcodes no domain value.
Items are candidates (``verification="candidate"``); curation-only axes are left
null / "unspecified" and never fabricated. The extractor confirms nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path

# ── unit segmentation ────────────────────────────────────────────
ARTICLE_RE = re.compile(r"(?m)^\s*(Article|Artikel)\s+(\d+[a-z]?)\b")
RECITAL_RE = re.compile(r"(?m)^\s*\((\d{1,3})\)\s")     # numbered recitals "(1) "


# C0 control chars a PDF/text layer can emit that break strict CSV parsing and pollute
# claim text — everything below 0x20 except TAB and NEWLINE (and DEL). Stripped at ingestion,
# before segmentation, so span offsets stay consistent with the cleaned text.
_CTRL_DELETE = {c: None for c in range(0x20) if c not in (0x09, 0x0A)}
_CTRL_DELETE[0x7F] = None


def clean_text(s: str) -> str:
    """Remove NUL and other control characters (keep tab/newline) from extracted text."""
    return s.translate(_CTRL_DELETE) if s else s


# ── adaptive space inference (ADR-002) ───────────────────────────
# A PDF text layer inserts a space between two glyphs only when their horizontal gap exceeds
# a threshold; justified/tightly-kerned PDFs have inter-word gaps below the default, so words
# merge ("derAnspruchaufHerstellung…"). A single global threshold cannot win: lowering it
# shatters loosely-tracked words. Instead each LINE's own glyph-gap distribution is used to
# find the natural word-break, so tight-merged and loose-tracked lines are both handled and
# clean/uniform lines are left untouched. Pure geometry — no vocabulary, no model, no network.
_SPACE_MIN_GAP_PT = 0.45     # a break must clear this absolute margin above baseline (pt)
_SPACE_GAP_RATIO = 0.05      # …or this fraction of the line's median glyph size
_INTRA_PCTL = 0.35           # low percentile of gaps ≈ the intra-word spacing baseline


def _line_break_threshold(gaps, size: float):
    """The word-break gap threshold for one line: the intra-word spacing *baseline* plus a
    margin, so EVERY inter-word gap on the line is split — not just the widest one.

    Word gaps on a real (justified) line vary (a wider gap after a period, stretched spaces),
    while intra-word char gaps form a dense low cluster. Splitting at the single largest jump
    would lock onto the widest gap and merge all the narrower-but-genuine word boundaries; so
    instead the baseline is a low percentile of the gaps (the intra-word cluster) and the
    threshold is baseline + max(floor_pt, ratio·size). Returns ``None`` when no gap clears the
    threshold (a single word / uniform tracking) so nothing is spuriously split.
    """
    xs = sorted(gaps)
    if len(xs) < 2:
        return None
    baseline = xs[int(_INTRA_PCTL * (len(xs) - 1))]
    thr = baseline + max(_SPACE_MIN_GAP_PT, _SPACE_GAP_RATIO * size)
    if xs[-1] < thr:
        return None                       # no gap exceeds baseline+margin → leave intact
    return thr


def _infer_line_text(line) -> str:
    """Reconstruct one line's text from its glyphs, inserting spaces at inferred word breaks.

    ``line`` is a pdfplumber ``extract_text_lines`` entry (``chars`` + ``text``). The line is
    trusted unchanged when the PDF already emitted space glyphs; otherwise spaces are inferred
    from the line's own gap distribution (:func:`_line_break_threshold`). A uniformly spaced
    line (a single letter-tracked word, or spaced single characters) has no gap exceeding
    baseline+margin, so ``_line_break_threshold`` returns ``None`` and the glyphs are joined
    unchanged — no separate guard is needed and no word is shattered.
    """
    chars = line.get("chars") or []
    fallback = line.get("text") or "".join(c.get("text", "") for c in chars)
    cs = sorted(chars, key=lambda c: c.get("x0", 0.0))
    if len(cs) < 2:
        return fallback
    if any(c.get("text") == " " for c in cs):
        return fallback
    gaps = [cs[i + 1].get("x0", 0.0) - cs[i].get("x1", 0.0) for i in range(len(cs) - 1)]
    sizes = [c.get("size") or 0.0 for c in cs]
    sizes = [s for s in sizes if s > 0]
    size = (sorted(sizes)[len(sizes) // 2] if sizes else 10.0) or 10.0
    thr = _line_break_threshold(gaps, size)
    if thr is None:
        return "".join(c.get("text", "") for c in cs)
    out = [cs[0].get("text", "")]
    for i, g in enumerate(gaps):
        if g >= thr:
            out.append(" ")
        out.append(cs[i + 1].get("text", ""))
    return "".join(out)


def _table_bboxes(page) -> list[tuple]:
    """Bounding boxes of the page's detected (ruled) tables; empty on any failure."""
    try:
        return [t.bbox for t in page.find_tables()]
    except Exception:
        return []


def _in_table(line, bboxes) -> bool:
    """True when the line lies inside a table region: its vertical centre falls within a
    table bbox and at least half of its width overlaps that bbox horizontally (so prose
    beside a narrow table survives)."""
    top, bottom = line.get("top"), line.get("bottom")
    if top is None or bottom is None:
        return False
    yc = (top + bottom) / 2
    x0, x1 = line.get("x0", 0.0), line.get("x1", 0.0)
    width = (x1 - x0) or 1.0
    for bx0, btop, bx1, bbot in bboxes:
        if btop <= yc <= bbot and (min(x1, bx1) - max(x0, bx0)) / width >= 0.5:
            return True
    return False


def extract_text(pdf_path: str, skip_tables: bool = True) -> str:
    """Extract page text with adaptive per-line space inference (ADR-002).

    Uses pdfplumber's own line detection (``extract_text_lines``) for reading order, then
    repairs merged words per line from glyph geometry. Falls back to plain ``extract_text``
    for any page whose line extraction yields nothing (e.g. no positioned glyphs).

    ``skip_tables`` (default) drops lines inside detected ruled-table regions: table cells
    read as word salad once linearised ("Datum date YYYY MM DD"), which pollutes claim
    extraction and downstream term mining. Table *detection* is geometric (ruling lines),
    never content-based; the fallback path has no geometry, so nothing is dropped there."""
    import pdfplumber
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            try:
                lines = page.extract_text_lines()
            except Exception:
                lines = None
            if lines:
                bboxes = _table_bboxes(page) if skip_tables else []
                if bboxes:
                    lines = [ln for ln in lines if not _in_table(ln, bboxes)]
                parts.append("\n".join(
                    _infer_line_text(ln) if ln.get("chars")
                    else (ln.get("text") or "") for ln in lines))
            else:
                parts.append(page.extract_text() or "")
    return clean_text("\n".join(parts))


def _spans_from(matches, text, kind, id_fn):
    units = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        units.append({"unit_id": id_fn(m), "unit_type": kind,
                      "start": start, "end": end, "text": text[start:end].strip()})
    return units


def segment_units(text: str) -> list[dict]:
    """Segment into articles > recitals > paragraphs (first that matches wins)."""
    arts = list(ARTICLE_RE.finditer(text))
    if len(arts) >= 3:
        return _spans_from(arts, text, "article", lambda m: f"Article-{m.group(2)}")
    recs = list(RECITAL_RE.finditer(text))
    if len(recs) >= 5:
        return _spans_from(recs, text, "recital", lambda m: f"Recital-{m.group(1)}")
    # fallback: blank-line paragraphs
    units, pos = [], 0
    for i, para in enumerate(re.split(r"\n\s*\n", text)):
        s = text.find(para, pos); pos = s + len(para)
        if len(para.strip()) >= 40:
            units.append({"unit_id": f"para-{i}", "unit_type": "paragraph",
                          "start": s, "end": s + len(para), "text": para.strip()})
    return units


def _quantification(sentence: str, profile) -> str:
    low = sentence.lower()
    for value, cues in profile.quant_cues:
        if any(c in low for c in cues):
            return value
    return "null"


def _marker_regex(pattern: str):
    """A word-boundary matcher for a surface marker: the pattern must not sit INSIDE a larger
    word ("might" ≠ "mighty", "allows" ≠ "swallows", "fined" ≠ "defined"). Boundaries are added
    only at word-character edges so multi-word / punctuated markers still match."""
    esc = re.escape(pattern)
    left = r"(?<!\w)" if pattern[:1].isalnum() else ""
    right = r"(?!\w)" if pattern[-1:].isalnum() else ""
    return re.compile(left + esc + right, re.IGNORECASE)


def candidate_items(unit: dict, source_urn: str, profile) -> list[dict]:
    items, seen = [], set()
    text, base = unit["text"], unit["start"]
    for pattern, predicate, modality in profile.markers:
        for m in _marker_regex(pattern).finditer(text):
            # one item per (predicate, sentence) to avoid double-counting overlaps
            s_start = text.rfind(".", 0, m.start()) + 1
            s_end = text.find(".", m.end())
            s_end = len(text) if s_end == -1 else s_end + 1
            sentence = text[s_start:s_end].strip()
            key = (predicate, s_start)
            if key in seen or len(sentence) < 8:
                continue
            seen.add(key)
            polarity = "N" if modality in profile.modalities_n else "D"
            span = [base + s_start, base + s_end]
            iid = "item-" + hashlib.sha1(
                f"{source_urn}{span}{predicate}".encode()).hexdigest()[:10]
            items.append({
                "item_id": iid,
                "source_urn": source_urn,
                "unit_id": unit["unit_id"],
                "unit_type": unit["unit_type"],
                "span": span,
                "marker": pattern,
                "text": sentence[:400],
                # closed axes (candidate; curator confirms)
                "polarity": polarity,
                "type": "is" if polarity == "D" else "ought",
                "predicate": predicate,
                # Federation-5D: universal edge-reasoning dimension. The local predicate
                # remains the finer profile meaning and is never replaced by this projection.
                "dimension": profile.dimension_for(predicate),
                "modality": modality,
                "quantification": _quantification(sentence, profile),
                # left for curation — never fabricated
                "principle": None,
                "judicial_canon": "null",
                "inference_rule": "unspecified",
                "confidence": None,
                "verification": "candidate",
            })
    return items


# ── definition scan (P1: quoted term + a profile def-verb) ───────
# Vocabulary (which verbs are definitional) comes from the profile; this module
# hardcodes only the language-neutral label-hygiene word lists.
_OPEN_Q = "‘'\"“"
_CLOSE_Q = "’'\"”"
# strip these off either end of a candidate term
_DEF_STRIP = {"the", "a", "an", "and", "or", "by", "of", "to", "for", "such", "any"}
# a term that still ENDS in one of these is a fragment -> reject
_DEF_CONJ = {"and", "or", "by", "of", "to", "for"}


def _term_slug(s: str) -> str:
    from ..concept.morph import transliterate
    return re.sub(r"[^a-z0-9]+", "-", transliterate(s)).strip("-")


def clean_term(raw: str) -> str | None:
    """Label hygiene: collapse whitespace, strip edge stopwords/conjunctions, and
    reject empty / >4-content-word / conjunction-terminated fragments. Returns the
    cleaned term or ``None`` if it should be dropped."""
    words = re.sub(r"\s+", " ", raw).strip().split()
    while words and words[0].lower() in _DEF_STRIP:
        words.pop(0)
    while words and words[-1].lower() in (_DEF_STRIP - _DEF_CONJ):
        words.pop()  # strip trailing stopwords that are not conjunctions
    if not words:
        return None
    if words[-1].lower() in _DEF_CONJ:
        return None  # ends in a conjunction/preposition -> fragment
    if len(words) > 4:
        return None
    return " ".join(words)


def definitions(text: str, source_urn: str, profile) -> list[dict]:
    """Scan FULL source text for a quoted term immediately followed by one of the
    profile's ``def_verbs``. Returns clean entity-concept seeds:
    ``{term, term_slug, span_start, span_end, source_urn}``. Deterministic; the
    definitional vocabulary is the profile's, never hardcoded here."""
    verbs: frozenset[str] = getattr(profile, "def_verbs", frozenset())
    if not verbs:
        return []
    verb_alt = "|".join(re.escape(v) for v in sorted(verbs, key=len, reverse=True))
    pat = re.compile(
        "[" + _OPEN_Q + "]"
        r"([A-Za-zÄÖÜäöüß][\w .\-]{2,40}?)"
        "[" + _CLOSE_Q + "]"
        r"\s+(?:" + verb_alt + r")\b",
        re.IGNORECASE)
    out, seen = [], set()
    for m in pat.finditer(text):
        term = clean_term(m.group(1))
        if not term:
            continue
        slug = _term_slug(term)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append({"term": term, "term_slug": slug,
                    "span_start": m.start(1), "span_end": m.end(1),
                    "source_urn": source_urn})
    return out


def extract(pdf_path: str, source_urn: str, profile) -> dict:
    text = extract_text(pdf_path)
    units = segment_units(text)
    items = [it for u in units for it in candidate_items(u, source_urn, profile)]
    return {
        "source_urn": source_urn,
        "pdf": Path(pdf_path).name,
        "n_chars": len(text),
        "n_units": len(units),
        "unit_type": units[0]["unit_type"] if units else None,
        "n_items": len(items),
        "profile": profile.id,
        "text": text,
        "units": units,
        "items": items,
    }


def urn_from_filename(name: str, profile) -> str:
    """Mint a URN from a filename using the profile's namespace (opaque key)."""
    decoded = urllib.parse.unquote(name)
    slug = re.sub(r"[^a-z0-9]+", "-", Path(decoded).stem.lower()).strip("-")
    return f"urn:{profile.namespace}:source:{slug}"


def main() -> int:
    from ..profile import get_profile
    import versum.profiles  # noqa: F401  (register built-in profiles)
    ap = argparse.ArgumentParser(description="Extract candidate claim items from a PDF.")
    ap.add_argument("pdf")
    ap.add_argument("--profile", default="generic")
    ap.add_argument("--urn", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    profile = get_profile(args.profile)
    urn = args.urn or urn_from_filename(Path(args.pdf).name, profile)
    result = extract(args.pdf, urn, profile)
    if args.out:
        Path(args.out).write_text(
            "\n".join(json.dumps(it, ensure_ascii=False) for it in result["items"]) + "\n",
            encoding="utf-8")
    summary = {k: result[k] for k in
               ("source_urn", "pdf", "n_chars", "n_units", "unit_type", "n_items", "profile")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
