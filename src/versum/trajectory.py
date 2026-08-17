"""Trajectories — an agent's action sequence as an ordinary process composition.

An action sequence ordered in time is already a shape this engine composes: a
``PROCESS`` composition, whose ``step`` participants carry positions and must each
be grounded in evidence. A trajectory is therefore not a new kind of object, and
this module deliberately adds no schema — it builds the composition the concept
layer already validates, and refuses the ones it would reject.

Two properties come from that reuse rather than from anything written here, and
both are what a reviewer actually needs:

*Every step must be grounded.* ``Composition.violations`` rejects a participant
with no evidence, so a trajectory cannot be asserted without the actions that
support it. A narrative about what an agent did, unattached to the record of it
doing so, is exactly the unfalsifiable artefact this engine exists to refuse.

*Grounding runs both directions.* Given an action one can ask which readings of
the run it supports — :func:`readings_grounded_by`. An action log answers the
forward question only ("what happened next"), and the backward question is the
one a reviewer needs when a trajectory looks wrong: *what else did this step feed?*

**Boundary.** This module composes and grounds. It does not decide whether a
trajectory served the purpose it was given — that comparison needs a mandate and
a judgement, and both belong to a consumer. Compositions are emitted as
``candidate``; the engine proposes a reading and confirms nothing.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from .composition import Composition, CompositionKind, Participant

__all__ = ["Step", "trajectory", "readings_grounded_by", "steps_of"]

#: One step: the action, and the evidence ids that ground it having happened.
Step = tuple[str, Sequence[str]]


def trajectory(
    composition_id: str,
    steps: Iterable[Step],
    *,
    label: str = "",
    method_version: str = "",
    nd_scope: Mapping | None = None,
) -> Composition:
    """Build a ``PROCESS`` composition from an ordered action sequence.

    ``steps`` is an ordered iterable of ``(action_ref, evidence_ids)``. Order is
    the caller's — this engine does not sort actions, because inferring sequence
    from timestamps or ids would be guessing at structure the caller knows.

    The returned composition is a *candidate*, and is **not** validated here:
    call ``.violations()`` as with any other composition. That keeps one
    validation path rather than a second, softer one for trajectories — a
    trajectory with a single step, or a step with no grounding evidence, is
    rejected by the same rules that reject any malformed process.
    """
    participants = tuple(
        Participant(role="step", target_id=str(action),
                    evidence_ids=tuple(str(e) for e in (evidence or ())),
                    position=index)
        for index, (action, evidence) in enumerate(steps)
    )
    return Composition(
        composition_id=str(composition_id),
        kind=CompositionKind.PROCESS.value,
        participants=participants,
        label=label,
        verification="candidate",
        method_version=method_version,
        nd_scope=dict(nd_scope or {}),
    )


def steps_of(composition: Composition) -> tuple[Participant, ...]:
    """The step participants of a process composition, in declared order.

    Sorted by ``position`` where present, and otherwise left in declaration
    order — never re-derived from anything else.
    """
    steps = tuple(p for p in composition.participants
                  if p.role.split(":", 1)[0] == "step")
    if all(p.position is not None for p in steps):
        return tuple(sorted(steps, key=lambda p: p.position))
    return steps


def readings_grounded_by(
    evidence_id: str, compositions: Iterable[Composition]
) -> tuple[str, ...]:
    """Which composed readings this one action supports.

    The backward direction of many-to-many grounding, and the question an action
    log cannot answer: given a step, what else does it feed? A reviewer who
    doubts one action needs to know every reading that rests on it, not just the
    one they happened to open.

    Returns composition ids, sorted, without duplicates.
    """
    ref = str(evidence_id)
    hits = {
        c.composition_id
        for c in compositions
        for p in c.participants
        if ref in p.evidence_ids
    }
    return tuple(sorted(hits))
