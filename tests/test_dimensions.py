from versum.dimensions import COMPOSITION_TABLE, Dimension, compose, dimension_values
from versum.profile import get_profile
import versum.profiles  # noqa: F401


def test_federation_values_and_algebra_are_stable():
    assert dimension_values() == {
        "structural", "causal", "intentional", "temporal", "relational"}
    assert len(COMPOSITION_TABLE) == 25
    assert compose(Dimension.STRUCTURAL, Dimension.CAUSAL) == Dimension.CAUSAL
    assert compose("relational", "structural") == Dimension.STRUCTURAL


def test_all_built_in_profile_predicates_project_to_federation():
    # law-eu is the one profile with predicates deliberately left unmapped (Round 5): its
    # four normative predicates ("grants", "imposes", "permits", "prohibits" — each an
    # operator O/P/F or a Hohfeldian right/duty) carry no 5D dimension, so they carry no
    # entry in the table at all (see versum.profiles.law_eu.PREDICATE_DIMENSIONS and
    # tests/test_deontic_plane_law_eu.py). Every other built-in profile still maps every
    # predicate it declares.
    normative = frozenset({"grants", "imposes", "permits", "prohibits"})
    for profile_id in ("generic", "law-eu", "news", "scholarly"):
        profile = get_profile(profile_id)
        if profile_id == "law-eu":
            assert profile.unmapped_predicates() == normative
        else:
            assert profile.unmapped_predicates() == frozenset()
        # dimension_for still resolves every predicate (unmapped ones fall to the
        # relational floor), and every resolved value is one of the five dimensions.
        assert {profile.dimension_for(p) for p in profile.predicates} <= dimension_values()


def test_extracted_claim_preserves_local_predicate_and_universal_dimension():
    from versum.io.extract import candidate_items
    p = get_profile("generic")
    rows = candidate_items({"text": "Heat causes expansion.", "start": 0,
                            "unit_id": "p1", "unit_type": "paragraph"},
                           "urn:x:1", p)
    assert rows[0]["predicate"] == "causes"
    assert rows[0]["dimension"] == "causal"
