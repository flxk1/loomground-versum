# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""The `delegation` profile: a mandate becomes an ordinary span claim.

The property under test is that nothing about a mandate is special. It is read from
a source, anchored to exact offsets, drawn from a closed vocabulary and checked by
the invariants every other claim is checked by — because a purpose asserted at
runtime cannot be checked by a supervisor, and a purpose anchored to the document
that conferred it can be checked by anyone holding the document.

These tests also pin the boundary: the profile supplies vocabulary, and the engine
stores what it reads. Whether a trajectory served its mandate is a judgement, and
this engine must not acquire the ability to make it.
"""
from __future__ import annotations

import versum.profiles  # noqa: F401 — importing registers the built-in profiles
from versum.profile import PROFILES, get_profile

FEDERATION_5D = {"structural", "causal", "intentional", "temporal", "relational"}


def _p():
    return get_profile("delegation")


# --- it is an ordinary profile ------------------------------------------------

def test_profile_registers_like_any_other():
    assert _p().id == "delegation"
    assert "delegation" in PROFILES


def test_every_predicate_projects_onto_a_federation_axis():
    p = _p()
    assert set(p.predicate_dimensions) == p.predicates, "predicate/dimension mismatch"
    assert set(p.predicate_dimensions.values()) <= FEDERATION_5D


def test_vocabulary_is_closed():
    # A closed vocabulary is what stops the base layer fabricating. An unrecognised
    # phrasing must yield no claim rather than a guessed one.
    p = _p()
    assert "invents" not in p.predicates
    for _, predicate, modality in p.markers:
        assert predicate in p.predicates, predicate
        assert modality in p.modalities, modality


def test_declares_no_identifier_scheme():
    # A mandate lives in whatever document conferred it; there is no domain URN
    # scheme to mint, so the write guard falls to the path-slug rather than
    # inventing one.
    assert _p().source_identifiers == ()


# --- purpose is intentional, revocation is causal ------------------------------

def test_purpose_predicates_are_intentional():
    # Federation-5D has an intentional axis; purpose is what it is for.
    dims = _p().predicate_dimensions
    assert dims["mandates"] == "intentional"
    assert dims["restricts"] == "intentional"


def test_revocation_is_causal_not_relational():
    # Revoking changes a position rather than describing one.
    assert _p().predicate_dimensions["revokes"] == "causal"


def test_carries_the_terms_a_delegation_chain_needs():
    # The governance language models conferral, purpose narrowing and onward
    # release; a profile that could not read those from a source would leave the
    # second term of every divergence comparison ungrounded.
    assert {"delegates", "mandates", "restricts", "consigns", "revokes"} <= _p().predicates


# --- surface cues are conservative --------------------------------------------

def test_purpose_cues_are_recognised():
    surfaces = {m[0]: m[1] for m in _p().markers}
    assert surfaces["for the purpose of"] == "mandates"
    assert surfaces["solely for"] == "restricts"
    assert surfaces["on behalf of"] == "delegates"


def test_markers_are_lowercase_substrings_like_every_other_profile():
    for surface, _, _ in _p().markers:
        assert surface == surface.lower()
        assert surface.strip() == surface


# --- the boundary --------------------------------------------------------------

def test_profile_carries_no_reasoning():
    # Values only. A profile that shipped a callable would have started deciding.
    p = _p()
    for name in ("predicates", "modalities", "markers", "predicate_dimensions"):
        value = getattr(p, name)
        flat = value.values() if hasattr(value, "values") else value
        for item in flat:
            assert not callable(item), f"{name} carries a callable"


def test_profile_states_no_verdict_vocabulary():
    # Whether a trajectory served its mandate is a consumer's judgement. If this
    # vocabulary ever grows a verdict term, the engine has started answering it.
    p = _p()
    for forbidden in ("diverges", "complies", "violates", "satisfies", "breaches"):
        assert forbidden not in p.predicates


def test_core_does_not_know_this_profile_exists():
    # Domain neutrality: the framework resolves profiles by id at call time and
    # names none of them. A core that mentioned `delegation` would be leaking.
    import versum.profile as core
    src = __import__("inspect").getsource(core)
    assert "delegation" not in src.lower()
