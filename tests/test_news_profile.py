"""Phase 3 loop-7 (news side, ADR-D4): the news event/fact profile.

The news profile is a valid Profile, extracts at least one event claim from a news snippet
('The Commission announced ...'), and is domain-distinct from law-eu (disjoint predicate
vocabulary, its own namespace). Profiles ARE allowed domain vocabulary — only the CORE
must stay neutral.
"""
from versum.profile import Profile, get_profile
from versum.identity.fingerprint import fingerprint
from versum.io import extract as ex
from versum.profiles.news import PROFILE as NEWS
from versum.profiles.law_eu import PROFILE as LAW
import versum.profiles  # noqa: F401 — register built-ins


def test_news_profile_is_valid_and_registered():
    assert isinstance(NEWS, Profile)
    assert get_profile("news") is NEWS
    assert NEWS.namespace == "news"
    assert NEWS.predicates and "announced" in NEWS.predicates
    # reporting modalities, not deontic force
    assert NEWS.modalities == frozenset({"asserted", "reported", "null"})


def test_news_profile_extracts_an_event_claim():
    text = ("The Commission announced a new set of measures today. "
            "The agency launched a public consultation.\n")
    urn = "urn:news:doc:demo"
    units = ex.segment_units(text)
    items = [it for u in units for it in ex.candidate_items(u, urn, NEWS)]
    assert items, "no event claims extracted from the news snippet"
    preds = {it["predicate"] for it in items}
    assert "announced" in preds
    # every extracted event is a valid predicate under the news profile
    for it in items:
        assert NEWS.is_valid("predicate", it["predicate"])
        assert NEWS.is_valid("modality", it["modality"])
        # polarity present; news is descriptive (no reporting stance is normative)
        assert it["polarity"] == "D"

    # the fingerprint takes the news profile's fixed shape
    fp = fingerprint(urn, items, NEWS)
    assert set(fp["dim5"]["predicate"]) == set(NEWS.predicates)
    assert fp["nd"]["namespace"] == "news"
    assert fp["dim5"]["predicate"]["announced"] >= 1


def test_news_profile_is_domain_distinct_from_law_eu():
    # event predicates and deontic predicates share nothing
    assert NEWS.predicates.isdisjoint(LAW.predicates)
    # separate URN namespaces (no collision of URN spaces)
    assert NEWS.namespace != LAW.namespace
    # news carries no legal principle / deontic modality vocabulary
    assert NEWS.principles == frozenset()
    assert "obliged" not in NEWS.modalities
