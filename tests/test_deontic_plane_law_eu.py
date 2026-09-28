"""D1 in the law-eu profile, Round 5: a deontic/normative predicate ("grants", "imposes",
"permits", "prohibits") takes NO 5D dimension from the deontic plane's operator binding —
and, since Round 5, no static-literal stand-in for one either. The plane's own binding is
always ``{}`` (an operator is an ought, not a fact on the 5D manifold); Round 4's own
workaround (assigning those predicates the relational floor as a literal table entry) is
itself corrected here: a table entry, even one that names the relational floor, is still a
predicate -> dimension MAPPING for a normative predicate, which Round 5 removes. The four
normative predicates simply have no entry in ``law_eu.PREDICATE_DIMENSIONS`` at all; the
relational floor they still land on comes only from the framework's own
unmapped-predicate default (``versum.profile.Profile.dimension_for`` ->
``versum.dimensions.DEFAULT_DIMENSION``), never from a per-predicate literal in this
profile (plane-fit rule 2: no local copy of a plane's data, and no read of it either, once
the plane publishes nothing to read)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from versum import deontic as deontic_mod
from versum.dimensions import DEFAULT_DIMENSION
from versum.profile import get_profile
from versum.profiles import law_eu

import deontic  # noqa: E402 — a hard dependency; never skipped

NORMATIVE_PREDICATES = ("grants", "imposes", "permits", "prohibits")


def test_deontic_operators_bind_to_nothing():
    assert deontic_mod.deontic_binding() == {}


def test_normative_predicates_carry_no_dimension_mapping_at_all():
    pd = law_eu.PREDICATE_DIMENSIONS
    # Round 5: none of the four normative predicates has ANY entry in the table — not
    # even one that names the relational floor.
    assert not (set(NORMATIVE_PREDICATES) & set(pd))
    profile = get_profile("law-eu")
    assert set(NORMATIVE_PREDICATES) <= profile.unmapped_predicates()
    # dimension_for still resolves them, but only via the framework's own unmapped-value
    # default, never a mapping this profile asserts.
    for predicate in NORMATIVE_PREDICATES:
        assert profile.dimension_for(predicate) == DEFAULT_DIMENSION.value == "relational"


def test_law_eu_never_reads_the_deontic_plane_binding():
    src = Path(law_eu.__file__).read_text(encoding="utf-8")
    assert "deontic_binding" not in src
    assert not [line for line in src.splitlines()
                if "import" in line and "deontic" in line.lower()]


def test_no_literal_operator_to_dimension_mapping_remains_in_law_eu():
    # No mapping from a deontic predicate/operator letter to ANY dimension — relational
    # included — may reappear, under any key spelling, anywhere in this profile's table.
    src = Path(law_eu.__file__).read_text(encoding="utf-8")
    literal = re.compile(
        r"""["'](?:grants|imposes|permits|prohibits|forbids|O|P|F)["']\s*:\s*["']"""
        r"""(?:causal|intentional|temporal|structural|relational)["']""")
    assert literal.findall(src) == []


def test_mutation_probe_a_reintroduced_operator_binding_is_not_silently_adopted(monkeypatch):
    """A synthetic, deliberately adversarial fixture (never a statement of this
    project's own position — see the module docstring): if the deontic plane's binding
    were ever mutated back to name a non-relational dimension for each operator letter,
    the law-eu profile's predicate dimensions must NOT change — because there is no entry
    for any normative predicate left to change. ``law_eu.PREDICATE_DIMENSIONS`` is a
    static literal that never calls the deontic plane's binding, so there is no read path
    left for a reintroduced binding to flow through. This is isolation by construction (an
    absent read path, and now also an absent table entry), not a runtime fail-closed
    check: proven here by mutating the live binding the versum boundary reads and showing
    the mutation is real (visible through :func:`versum.deontic.deontic_binding`) while
    law_eu.PREDICATE_DIMENSIONS is provably unaffected.
    """
    dim_a, dim_b = "structural", "temporal"  # any two non-relational dimensions will do
    reintroduced = {"O": dim_a, "P": dim_b, "F": dim_a}
    monkeypatch.setattr(deontic_mod, "deontic_binding", lambda: dict(reintroduced))
    assert deontic_mod.deontic_binding() == reintroduced  # the mutation is real and live
    for predicate in NORMATIVE_PREDICATES:
        assert predicate not in law_eu.PREDICATE_DIMENSIONS
    profile = get_profile("law-eu")
    for predicate in NORMATIVE_PREDICATES:
        assert profile.dimension_for(predicate) == "relational"


def test_d7_dimensions_vocabulary_is_untouched():
    # D7 is open: the pack's dimensions.json still lists conditional and defeasible.
    names = [d["name"] for d in deontic.vocabulary("dimensions")["dimensions"]]
    assert names == ["causal", "intentional", "temporal", "conditional", "defeasible"]
