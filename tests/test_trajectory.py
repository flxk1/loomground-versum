# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Trajectories: an action sequence as an ordinary process composition.

Nothing here should be special. The tests that matter check that reuse is real —
a trajectory is validated by the same rules as any other process, and an
ungrounded one is refused by them rather than by anything written for this case —
and that grounding runs backward, which is the direction an action log cannot
answer and a reviewer needs when a run looks wrong.
"""
from __future__ import annotations

from versum.composition import Composition, CompositionKind
from versum.trajectory import readings_grounded_by, steps_of, trajectory


def _run():
    return trajectory("traj-1", [
        ("read the brief", ["act#1"]),
        ("query the supplier db", ["act#2", "act#3"]),
        ("place the order", ["act#4"]),
    ], label="procurement run")


# --- it is an ordinary process composition ------------------------------------

def test_a_trajectory_is_a_process_composition():
    t = _run()
    assert isinstance(t, Composition)
    assert t.kind == CompositionKind.PROCESS.value
    assert t.violations() == []


def test_it_is_a_candidate_reading_not_a_confirmed_one():
    # The engine proposes a reading of the run and confirms nothing.
    assert _run().verification == "candidate"


def test_order_is_recorded_and_preserved():
    assert [p.target_id for p in steps_of(_run())] == [
        "read the brief", "query the supplier db", "place the order"]
    assert [p.position for p in steps_of(_run())] == [0, 1, 2]


def test_order_is_the_callers_and_is_never_re_derived():
    # Inferring sequence from ids or timestamps would be guessing at structure
    # the caller already knows.
    t = trajectory("t", [("z", ["e1"]), ("a", ["e2"])])
    assert [p.target_id for p in steps_of(t)] == ["z", "a"]


# --- grounding is enforced by the existing rules, not by new ones --------------

def test_an_ungrounded_step_is_refused():
    # A narrative about what an agent did, unattached to the record of it doing
    # so, is exactly the unfalsifiable artefact this engine refuses.
    t = trajectory("t", [("did something", []), ("did more", ["e1"])])
    assert any("grounding evidence" in v for v in t.violations())


def test_a_one_step_trajectory_is_refused():
    t = trajectory("t", [("only step", ["e1"])])
    assert any("at least two step" in v for v in t.violations())


def test_refusal_comes_from_the_shared_validator():
    # If this module ever grows its own softer validation path, a trajectory
    # could pass where an equivalent process composition would fail.
    bad = trajectory("t", [("a", [])])
    assert bad.violations(), "malformed trajectory accepted"
    assert bad.violations() == Composition.from_dict(bad.to_dict()).violations()


# --- grounding runs both directions -------------------------------------------

def test_one_action_can_feed_several_readings():
    a = _run()
    b = trajectory("traj-3", [("audit the order", ["act#4"]), ("file it", ["act#9"])])
    assert readings_grounded_by("act#4", [a, b]) == ("traj-1", "traj-3")


def test_an_action_that_feeds_nothing_returns_empty():
    assert readings_grounded_by("act#999", [_run()]) == ()


def test_backward_grounding_is_deduplicated_and_sorted():
    t = trajectory("dup", [("x", ["e1", "e1"]), ("y", ["e1"])])
    assert readings_grounded_by("e1", [t, t]) == ("dup",)


# --- the boundary --------------------------------------------------------------

def test_the_module_renders_no_judgement_about_the_run():
    # Whether a trajectory served the purpose it was given needs a mandate and a
    # judgement, and both belong to a consumer.
    import inspect

    from versum import trajectory as mod
    src = inspect.getsource(mod)
    for forbidden in ("def diverge", "def complies", "def violates", "def evaluate"):
        assert forbidden not in src, forbidden


def test_no_schema_is_added_for_trajectories():
    # A trajectory must stay indistinguishable from any other process to every
    # consumer of the composition layer.
    t = _run()
    assert set(t.to_dict()) == set(Composition.from_dict(t.to_dict()).to_dict())
    assert t.kind in {k.value for k in CompositionKind}
