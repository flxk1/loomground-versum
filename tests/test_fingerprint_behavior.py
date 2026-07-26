"""More fingerprint coverage — fixed-shape dim5 histogram + exact counts.

Generic profile; a hand-built claim list. Also checks that claims from other sources are
excluded from a source's fingerprint.
"""
from versum.identity.fingerprint import fingerprint
from versum.profiles.generic import PROFILE as GENERIC

URN = "urn:kg:source:demo"
OTHER = "urn:kg:source:other"


def _claims():
    return [
        {"item_id": "i1", "source_urn": URN, "predicate": "defines",
         "modality": "definitional", "quantification": "definite"},
        {"item_id": "i2", "source_urn": URN, "predicate": "causes",
         "modality": "asserted", "quantification": "universal"},
        {"item_id": "i3", "source_urn": URN, "predicate": "causes",
         "modality": "asserted", "quantification": "universal"},
        # a claim from a DIFFERENT source must not count toward URN's fingerprint
        {"item_id": "i4", "source_urn": OTHER, "predicate": "causes",
         "modality": "asserted", "quantification": "null"},
    ]


def test_dim5_exact_counts():
    fp = fingerprint(URN, _claims(), GENERIC)
    assert fp["n_claims"] == 3  # OTHER's claim excluded
    d = fp["dim5"]
    assert d["predicate"]["causes"] == 2
    assert d["predicate"]["defines"] == 1
    assert d["modality"]["asserted"] == 2
    assert d["modality"]["definitional"] == 1
    assert d["quantification"]["universal"] == 2
    assert d["quantification"]["definite"] == 1
    # untouched buckets stay at zero, never absent
    assert d["predicate"]["relates"] == 0
    assert d["quantification"]["null"] == 0


def test_dim5_keys_are_profile_closed_sets():
    fp = fingerprint(URN, _claims(), GENERIC)
    d = fp["dim5"]
    assert set(d["predicate"]) == set(GENERIC.predicates)
    assert set(d["modality"]) == set(GENERIC.modalities)
    assert set(d["quantification"]) == set(GENERIC.quantifications)


def test_nd_namespace_matches_profile():
    fp = fingerprint(URN, _claims(), GENERIC)
    assert fp["nd"]["namespace"] == GENERIC.namespace == "kg"
    assert fp["profile"] == "generic"


def test_empty_source_gives_all_zero_fixed_shape():
    fp = fingerprint("urn:kg:source:nothing", _claims(), GENERIC)
    assert fp["n_claims"] == 0
    # shape is still the full closed set, all zeros
    assert set(fp["dim5"]["predicate"]) == set(GENERIC.predicates)
    assert sum(fp["dim5"]["predicate"].values()) == 0
