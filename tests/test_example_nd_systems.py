# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Every shipped nD-system example loads and validates.

`examples/nd-systems/` exists to show that a contextual coordinate system is added
by declarative configuration alone — no engine change. That claim is only worth
making if the shipped configurations actually load, and nothing checked them
before. An example that does not parse is worse than no example: it teaches the
wrong shape and fails at the reader's end rather than at ours.

The meaningful-human-control system additionally pins two properties it depends
on, because both are easy to lose in a later edit and both would silently
misreport oversight if lost.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from versum.nd import NDRegistry, load_system

EXAMPLES = sorted((Path(__file__).resolve().parent.parent
                   / "examples" / "nd-systems").glob("*.json"))


def test_examples_directory_is_not_empty():
    assert EXAMPLES, "no shipped nD-system examples found"


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_example_loads_and_validates(path):
    system = load_system(path)          # validate() raises on any violation
    assert system.violations() == []
    assert system.axes, f"{path.stem}: declares no axes"


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_example_registers_and_namespaces_its_axes(path):
    system = load_system(path)
    reg = NDRegistry()
    reg.register(system)
    for axis_id in system.axes:
        assert system.qualified_axis(axis_id) == f"{system.namespace}:{axis_id}"


# --- meaningful-human-control: the two properties it rests on ----------------

def _mhc():
    path = next(p for p in EXAMPLES if p.stem == "meaningful-human-control")
    return load_system(path)


def test_mhc_carries_the_five_constituents():
    assert set(_mhc().axes) == {
        "observability", "intervenability", "comprehensibility",
        "authority", "timeliness",
    }


def test_mhc_axes_are_ordered_so_two_claims_can_be_compared():
    # `precedes` is what makes "less control than" a checkable relation rather
    # than a matter of opinion. An axis without it is a label, not a scale.
    for axis_id, axis in _mhc().axes.items():
        assert "precedes" in axis.primitives, f"{axis_id} is unordered"
        assert axis.cardinality == "one"


def test_mhc_leaves_an_unassigned_axis_unknown_rather_than_zero():
    # The load-bearing one. An unmeasured constituent must not read as its
    # lowest level (which would report a failure nobody observed) and must not
    # read as satisfied (which would manufacture oversight). It reads unknown.
    system = _mhc()
    assert system.missing_coordinates == "preserve_unknown"
    assert "none" in system.axes["observability"].vocabulary  # a real floor exists...
    assert system.missing_coordinates != "default_lowest"     # ...and absence is not it


def test_mhc_rejects_a_value_outside_its_vocabulary():
    system = _mhc()
    assert system.unknown_values == "reject"
    assert system.axes["authority"].vocabulary_mode == "closed"


def test_mhc_requires_provenance_on_every_assignment():
    # A coordinate asserted by nobody in particular is the unfalsifiable claim
    # this decomposition exists to expose.
    system = _mhc()
    assert system.provenance_required
    assert all(a.provenance_required for a in system.axes.values())


def test_mhc_comprehensibility_separates_asserted_from_measured():
    # Four constituents can be read off a system; comprehensibility is a
    # property of the person reading, so the vocabulary must keep a claim that
    # someone understood distinct from a reader actually having been tested.
    vocab = _mhc().axes["comprehensibility"].vocabulary
    assert "asserted" in vocab
    assert any(v.startswith("measured") for v in vocab)


def test_mhc_stores_no_aggregate():
    # The multiplicative collapse is a reasoning step owned by a consumer. An
    # aggregate stored beside the coordinates would be a second place for the
    # two to disagree.
    axes = set(_mhc().axes)
    for forbidden in ("score", "overall", "aggregate", "effective_oversight", "total"):
        assert forbidden not in axes
