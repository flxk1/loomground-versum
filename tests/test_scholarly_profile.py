"""The scholarly profile: fires on academic prose with neutral (non-legal) predicates."""
import versum.profiles  # noqa: F401 — register built-ins
from versum.profile import get_profile
from versum.io import extract as ex
def _claims(text, profile_id):
    p = get_profile(profile_id)
    units = ex.segment_units(text)
    return [it for u in units for it in ex.candidate_items(u, "urn:sch:1", p)]


PROSE = ("Consciousness is defined as subjective experience. We argue that qualia cannot be "
         "reduced. The hard problem leads to explanatory gaps. This contradicts physicalism. "
         "Emergence enables higher-order properties.")


def test_registered():
    assert get_profile("scholarly").id == "scholarly"


def test_extracts_scholarly_predicates_not_legal():
    items = _claims(PROSE, "scholarly")
    preds = {it["predicate"] for it in items}
    assert "defines" in preds and "asserts" in preds and "causes" in preds
    # no legal deontic predicates leak in
    assert not ({"imposes", "permits", "prohibits", "obliges"} & preds)


def test_beats_law_eu_on_prose():
    assert len(_claims(PROSE, "scholarly")) > len(_claims(PROSE, "law-eu"))


def test_bilingual_markers_fire():
    de = ("Bewusstsein bedeutet subjektive Erfahrung. Emergenz führt zu neuen Eigenschaften. "
          "Diese These widerlegt den Reduktionismus.")
    preds = {it["predicate"] for it in _claims(de, "scholarly")}
    assert {"defines", "causes", "refutes"} <= preds, preds


def test_markers_match_on_word_boundaries_not_substrings():
    # regression (adversarial): a marker must not fire inside a larger word.
    items = _claims("This mighty claim swallows the point.", "scholarly")
    assert not any(it["marker"] in ("might", "allows") for it in items), \
        [it["marker"] for it in items]
    # but the real word still fires (sentence long enough to form a paragraph unit)
    assert _claims("The proposed model might indicate a significant trend in the dataset.",
                   "scholarly")
    # cross-profile: news 'fined' must not fire inside 'defined'
    fined = [it for it in _claims(
        "The appellate court carefully defined the disputed statutory term today.", "news")
        if it["predicate"] == "fined"]
    assert not fined


def test_hypothesized_is_normative_polarity():
    items = _claims("The model suggests that inflation may indicate demand shocks.", "scholarly")
    assert any(it["modality"] == "hypothesized" and it["polarity"] == "N" for it in items)
