"""More definition-scan + label-hygiene coverage (extract.definitions / clean_term).

Extends the definition tests with quote-glyph handling, law-eu German verbs,
multiple definitions in one text, span sanity, and per-profile def_verb scoping.

QUOTE GLYPHS: the regex accepts opening quotes {U+2018, ', ", U+201C} and closing
{U+2019, ', ", U+201D}. The German low-9 opening quote „ (U+201E) is NOT in the set,
so German text quoted as „Wort" is missed — these tests use the accepted straight/curly
glyphs, which the law-eu German definition verbs do match.
"""
from versum.io import extract as ex
from versum.profile import get_profile
import versum.profiles  # noqa: F401 — register built-ins


# ── hygiene through the full scan ────────────────────────────────
def test_hygiene_strips_padding_stopwords():
    defs = ex.definitions("'the personal data' means any information.",
                          "urn:kg:source:x", get_profile("generic"))
    assert len(defs) == 1
    assert defs[0]["term"] == "personal data"
    assert defs[0]["term_slug"] == "personal-data"


def test_hygiene_rejects_long_quoted_phrase():
    defs = ex.definitions("'one two three four five' means something.",
                          "urn:kg:source:x", get_profile("generic"))
    assert defs == []  # >4 content words dropped


def test_hygiene_rejects_conjunction_fragment():
    defs = ex.definitions("'purposes and' means the ends pursued.",
                          "urn:kg:source:x", get_profile("generic"))
    assert defs == []  # ends in a conjunction -> fragment


def test_multiple_definitions_in_one_text():
    text = "'Alpha' means the first item. Later, 'Beta' is defined as the second item."
    defs = ex.definitions(text, "urn:kg:source:x", get_profile("generic"))
    slugs = [d["term_slug"] for d in defs]
    assert slugs == ["alpha", "beta"]


# ── law-eu German definition verbs ───────────────────────────────
def test_law_eu_german_bezeichnet():
    # straight quotes (accepted); DE verb "bezeichnet"
    defs = ex.definitions('"Verantwortlicher" bezeichnet die entscheidende Stelle.',
                          "urn:dls:source:x", get_profile("law-eu"))
    assert [d["term_slug"] for d in defs] == ["verantwortlicher"]


def test_law_eu_german_gilt_als():
    defs = ex.definitions("'Verarbeitung' gilt als jeder Vorgang mit Daten.",
                          "urn:dls:source:x", get_profile("law-eu"))
    assert [d["term_slug"] for d in defs] == ["verarbeitung"]


def test_generic_ignores_german_verbs():
    # generic def_verbs are only {means, is defined as}; DE verbs must not fire
    defs = ex.definitions("'Verarbeitung' gilt als jeder Vorgang.",
                          "urn:kg:source:x", get_profile("generic"))
    assert defs == []


def test_profile_def_verb_scoping():
    gen = get_profile("generic")
    law = get_profile("law-eu")
    assert gen.def_verbs == frozenset({"means", "is defined as"})
    # law-eu is a superset that adds the German verbs
    assert gen.def_verbs <= law.def_verbs
    assert {"bezeichnet", "gilt als"} <= law.def_verbs


# ── span sanity ──────────────────────────────────────────────────
def test_span_within_text_and_ordered():
    text = "Preamble. 'Widget' means a small device used here."
    defs = ex.definitions(text, "urn:kg:source:x", get_profile("generic"))
    assert len(defs) == 1
    d = defs[0]
    assert 0 <= d["span_start"] < d["span_end"] <= len(text)
    assert "Widget" in text[d["span_start"]:d["span_end"]]
