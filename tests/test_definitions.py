"""The quoted-definition scan (P1) + label hygiene (P3).

Proves ``extract.definitions`` seeds clean slugs from ``'X' means …`` and that the
hygiene drops fragments (e.g. a trailing conjunction) rather than minting junk.
"""
from versum.io import extract as ex
from versum.profile import get_profile
import versum.profiles  # noqa: F401 — register built-ins


TEXT = (
    "In this note, 'personal data' means any information about a person. "
    "A 'data subject' means the person concerned. "
    "The term 'controller' is defined as the body that decides. "
    "Nothing here about 'processing by automated means and' purposes and other things."
)


def test_definitions_clean_slugs():
    profile = get_profile("generic")
    defs = ex.definitions(TEXT, "urn:kg:source:note", profile)
    slugs = {d["term_slug"] for d in defs}
    assert "personal-data" in slugs
    assert "data-subject" in slugs
    assert "controller" in slugs
    # every seed is a clean lowercase hyphen slug, span-anchored to the source
    for d in defs:
        assert d["term_slug"] == d["term_slug"].lower()
        assert " " not in d["term_slug"]
        assert d["source_urn"] == "urn:kg:source:note"
        assert 0 <= d["span_start"] < d["span_end"] <= len(TEXT)


def test_hygiene_drops_conjunction_fragment():
    # a quoted fragment ending in a conjunction must be rejected outright
    assert ex.clean_term("purposes and") is None
    assert ex.clean_term("processing by automated means and") is None
    # empty after stripping edge stopwords
    assert ex.clean_term("the of") is None
    # leading/trailing stopwords are stripped, not the whole term
    assert ex.clean_term("the personal data") == "personal data"
    # >4 content words rejected
    assert ex.clean_term("one two three four five") is None


def test_no_junk_from_noun_means():
    # "by automated means" (means as NOUN) must NOT seed a concept: no quoted term+verb
    profile = get_profile("generic")
    defs = ex.definitions("Data processed by automated means is common.", "urn:x", profile)
    assert defs == []
