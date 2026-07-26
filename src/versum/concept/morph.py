"""versum/morph.py — deterministic morphology normalization for key_term identity (ADR-003).

Inflected surface forms of the same term ("produkts" / "produkt" / "produkten") must converge
to ONE concept identity. This normalizes a key_term slug so its words map to a common stem —
deterministically, offline, no model. It names no domain value: morphology is *language*
structure (the same category as the function-word lists already in the core).

Two backends:
  * ``snowball`` — the ``snowballstemmer`` library (pure-python, offline, deterministic), used
    when a ``language`` is configured and the package is importable. Gold-standard accuracy.
  * ``suffix`` — a dependency-free, conservative, multilingual suffix stripper used when no
    language is set or Snowball is unavailable, so the engine still runs with no extra deps.

Identity uses the normalized form; the human label keeps the surface form (see canon), so
over-stemming only coarsens an id — it never garbles a displayed label. Normalization is
OFF unless a caller passes a language / enables it.
"""
from __future__ import annotations

import re
import unicodedata

# round-trip digraph expansions of German/Nordic orthography (ä→ae is the convention
# those spelling systems themselves use when ASCII is forced); everything else folds
# via NFKD accent stripping. Language structure, not vocabulary.
_TRANSLIT = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "æ": "ae", "ø": "oe", "å": "aa"}


def transliterate(s: str) -> str:
    """Deterministic ASCII folding for slug identity: digraph expansion first
    (``für`` → ``fuer``, never ``f-r``), then NFKD accent stripping (``é`` → ``e``)."""
    expanded = "".join(_TRANSLIT.get(ch, ch) for ch in (s or "").lower())
    return "".join(c for c in unicodedata.normalize("NFKD", expanded)
                   if not unicodedata.combining(c))

# conservative, ordered DE+EN *inflectional* (plural / case) endings for the dependency-free
# fallback. Ordered longest-first; only stripped when the remaining stem stays ≥ _MIN_STEM.
# DERIVATIONAL endings (-er agent noun, -ung, -lich, -heit, …) are deliberately EXCLUDED:
# they change meaning, so stripping them false-merges distinct words (Gläubiger/Gläubige,
# Wette/Wetter). This trades some recall for precision; use the Snowball backend for higher
# recall where its aggressiveness is acceptable. Language structure, not domain vocabulary.
_SUFFIXES = ("es", "en", "e", "s")
_MIN_STEM = 4

_SNOWBALL_LANGS = {
    "german", "english", "french", "spanish", "italian", "dutch", "portuguese",
    "danish", "swedish", "norwegian", "finnish", "russian", "romanian", "hungarian",
}

_stemmer_cache: dict = {}


def _snowball(language: str):
    """Return a cached Snowball stemmer for ``language`` or ``None`` if unavailable."""
    if language in _stemmer_cache:
        return _stemmer_cache[language]
    stemmer = None
    if language in _SNOWBALL_LANGS:
        try:
            import snowballstemmer
            stemmer = snowballstemmer.stemmer(language)
        except Exception:
            stemmer = None
    _stemmer_cache[language] = stemmer
    return stemmer


def _suffix_stem(word: str) -> str:
    """Conservative language-neutral suffix stripping (fallback backend)."""
    low = word.lower()
    for suf in _SUFFIXES:
        if low.endswith(suf) and len(low) - len(suf) >= _MIN_STEM:
            return low[: -len(suf)]
    return low


# an umlaut/ß in the word IS the language signal: only German(-family) orthography
# produces it, and the Snowball german stemmer's final step de-umlauts, which is the
# ONLY way ablaut plurals (Fall/Fälle/Fällen) converge on one identity. No language
# configuration is needed for this routing; without snowballstemmer installed the
# suffix stemmer still runs (umlaut plurals then stay split — graceful degradation).
_DE_SIGNAL = set("äöüß")


def stem_word(word: str, language: str | None = None) -> str:
    """Stem a single word. Snowball when ``language`` is set and available; umlaut-
    bearing words route to Snowball german even without a language (see _DE_SIGNAL);
    else the conservative suffix stemmer. Very short words (< _MIN_STEM) are returned
    unchanged."""
    if not word or len(word) < _MIN_STEM:
        return (word or "").lower()
    low = word.lower()
    if language:
        st = _snowball(language)
        if st is not None:
            return st.stemWord(low)
    elif _DE_SIGNAL & set(low):
        st = _snowball("german")
        if st is not None:
            return st.stemWord(low)
    return _suffix_stem(word)


def normalize(term_slug: str, language: str | None = None) -> str:
    """Normalize a key_term *slug* (hyphen-joined words) to a stem-joined identity form.

    Each word is stemmed and re-joined with hyphens; empties dropped. Deterministic. When
    ``language`` is falsy AND Snowball is unusable the conservative suffix stemmer still runs,
    so calling this always yields a stable, convergent key — pass ``language=None`` only from
    a caller that has decided normalization is wanted (the canon gates it on config).
    """
    if not term_slug:
        return term_slug
    parts = [p for p in re.split(r"-+", term_slug) if p]
    stemmed = [stem_word(p, language) for p in parts]
    return "-".join(s for s in stemmed if s)
