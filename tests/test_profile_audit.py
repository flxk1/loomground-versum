"""The profile audit (``Profile.federation_projections``) must agree with the
``profiles/law_eu.py`` Round 5 wording: a normative O/P/F predicate ("grants",
"imposes", "permits", "prohibits") carries NO cross-profile 5D dimension mapping —
it is not declared — and the audit output must say exactly that, rather than
reporting the framework's internal relational-floor fallback (the value
``Profile.dimension_for`` hands back to *callers* for any unmapped predicate) as
if the profile had declared it.

Without the fix, ``federation_projections`` calls ``dimension_for`` unconditionally
and reports ``federation_dimension: "relational"`` / ``verification:
"profile-declared"`` for every normative predicate too — silently contradicting the
"not declared" wording in ``profiles/law_eu.py`` (~L137-150) and in
``Profile.dimension_for``'s own docstring (~L64-71). This test fails on that
pre-fix behavior.
"""
from __future__ import annotations

from versum.profile import get_profile
from versum.profiles import law_eu  # noqa: F401 — registers "law-eu"

NORMATIVE_PREDICATES = ("grants", "imposes", "permits", "prohibits")


def test_normative_predicates_are_unmapped_on_the_profile():
    profile = get_profile("law-eu")
    unmapped = profile.unmapped_predicates()
    for predicate in NORMATIVE_PREDICATES:
        assert predicate in unmapped, (
            f"{predicate!r} must stay out of predicate_dimensions (Round 5)"
        )


def test_audit_reports_normative_predicates_as_not_declared():
    profile = get_profile("law-eu")
    projections = {p["local_predicate"]: p for p in profile.federation_projections()}

    for predicate in NORMATIVE_PREDICATES:
        entry = projections[predicate]
        assert entry["federation_dimension"] is None, (
            f"audit must not report a dimension for unmapped/normative predicate "
            f"{predicate!r}; got {entry['federation_dimension']!r} (the relational-"
            f"floor fallback leaking into the audit as a false 'declared' mapping)"
        )
        assert entry["verification"] == "not_declared", (
            f"audit must mark {predicate!r} as 'not_declared', not "
            f"{entry['verification']!r}"
        )


def test_audit_still_reports_mapped_non_normative_predicates():
    profile = get_profile("law-eu")
    projections = {p["local_predicate"]: p for p in profile.federation_projections()}

    # "holds" is a genuinely mapped, non-normative predicate (see PREDICATE_DIMENSIONS
    # in profiles/law_eu.py) — the audit must still declare it normally.
    entry = projections["holds"]
    assert entry["federation_dimension"] == "relational"
    assert entry["verification"] == "profile-declared"


def test_dimension_for_is_unchanged_for_callers_that_need_a_concrete_value():
    # dimension_for() itself is a different contract (framework callers, e.g. the
    # extraction pipeline, that need a concrete placeholder) and must keep resolving
    # every predicate, including normative ones, to the relational floor. Only the
    # AUDIT surface (federation_projections) must say "not declared".
    profile = get_profile("law-eu")
    for predicate in NORMATIVE_PREDICATES:
        assert profile.dimension_for(predicate) == "relational"
