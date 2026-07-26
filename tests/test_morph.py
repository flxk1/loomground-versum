"""Morphology normalization (ADR-003): inflected key_term variants converge to one concept,
the label keeps a real surface form, and normalization is off by default.
"""
from versum.concept import morph, canon


def _claim(iid, urn, text, dom="d", predicate="imposes", polarity="D"):
    return {"item_id": iid, "canonical_urn": urn, "source_urn": urn, "text": text,
            "polarity": polarity, "predicate": predicate, "modality": "obliged",
            "quantification": "null", "domain": dom, "library": "L", "marker": "x"}


# ── morph module ────────────────────────────────────────────────────────────
def test_suffix_fallback_collapses_de_plurals():
    n = lambda s: morph.normalize(s, None)          # dependency-free fallback
    forms = {n("produkts"), n("produkten"), n("produkte"), n("produkt")}
    assert len(forms) == 1, forms


def test_snowball_when_language_set():
    st = morph._snowball("german")
    if st is None:
        import pytest; pytest.skip("snowballstemmer not installed")
    forms = {morph.normalize(s, "german")
             for s in ("produkts", "produkten", "produkte", "produkt")}
    assert len(forms) == 1


def test_short_words_untouched():
    assert morph.stem_word("eu", "german") == "eu"        # < min stem
    assert morph.normalize("ai", None) == "ai"


def test_multiword_slug_each_word_stemmed():
    out = morph.normalize("digitale-produkten", None)
    assert out.count("-") == 1 and "produkt" in out


# ── canon integration ───────────────────────────────────────────────────────
def _digital_product_claims():
    # same axis-signature, three inflected surface forms of one term, across 3 sources
    return [
        _claim("i1", "urn:x:1", "Das 'digitale Produkt' bleibt hier."),
        _claim("i2", "urn:x:2", "Ein 'digitales Produkt' entsteht dort."),
        _claim("i3", "urn:x:3", "Viele 'digitale Produkte' gelten auch."),
    ]


def test_morph_off_keeps_variants_separate():
    out = canon.build_canon(_digital_product_claims(), morph_language=None, min_df=1)
    # without normalization the inflected forms mint distinct concepts
    assert len(out["concepts"]) >= 2


def test_morph_auto_converges_variants_to_one_concept():
    out = canon.build_canon(_digital_product_claims(), morph_language="auto", min_df=1)
    assert len(out["concepts"]) == 1, list(out["concepts"])
    (agg,) = out["concepts"].values()
    assert len(agg["sources"]) == 3
    # label keeps a readable surface form, not the bare stem
    assert "produkt" in agg["surface_key_term"].lower()
    assert agg["label"] and agg["label"] != agg["concept_id"]


def test_fallback_keeps_agent_nouns_distinct_from_verbs():
    # regression (adversarial): the conservative fallback must NOT strip derivational -er, so
    # provider/provide, server/serve, printer/print stay distinct concepts.
    n = lambda s: morph.normalize(s, None)
    for agent_noun, verb in (("provider", "provide"), ("server", "serve"),
                             ("printer", "print"), ("reader", "read")):
        assert n(agent_noun) != n(verb), (agent_noun, verb, n(agent_noun))


def test_fallback_converges_de_ung_plurals():
    # regression: -ungen plural converges to the singular via -en (not over-stripped)
    n = lambda s: morph.normalize(s, None)
    assert n("leistungen") == n("leistung")
    assert n("obligations") == n("obligation")


def test_morph_does_not_over_merge_distinct_terms():
    claims = [
        _claim("i1", "urn:a:1", "A 'controller' has a duty."),
        _claim("i2", "urn:a:2", "A 'processor' has a duty."),
    ]
    out = canon.build_canon(claims, morph_language="auto", min_df=1)
    assert len(out["concepts"]) == 2      # controller != processor
