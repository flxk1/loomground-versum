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
    for profile_id in ("generic", "law-eu", "news", "scholarly"):
        profile = get_profile(profile_id)
        assert profile.unmapped_predicates() == frozenset()
        assert {profile.dimension_for(p) for p in profile.predicates} <= dimension_values()


def test_extracted_claim_preserves_local_predicate_and_universal_dimension():
    from versum.io.extract import candidate_items
    p = get_profile("generic")
    rows = candidate_items({"text": "Heat causes expansion.", "start": 0,
                            "unit_id": "p1", "unit_type": "paragraph"},
                           "urn:x:1", p)
    assert rows[0]["predicate"] == "causes"
    assert rows[0]["dimension"] == "causal"
