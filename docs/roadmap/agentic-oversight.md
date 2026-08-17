<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright 2026 flxk1 -->
# Roadmap slice — the knowledge plane and agentic oversight

Status: **draft, not committed scope.** Non-normative.

A set of open problems in agentic oversight reaches this engine as a question
about *evidence*: when a supervisor is told that an autonomous process went
wrong, what grounds that statement? This slice records the three places where
the engine is the right home for an answer, and the boundary that keeps it from
becoming the wrong one.

The engine's commitments are the frame. It privileges no domain, ships no model,
names no vendor, and makes no runtime decision. Every gap below is closed by
recording knowledge, never by governing it.

---

## V1 · A mandate is a claim, and it is not one yet

Delegated authority is conferred *for a purpose*. Detecting that an autonomous
process pursued the wrong objective requires comparing what it did against what
it was authorised to achieve — and that comparison is only as good as the record
of the second term.

A purpose asserted at runtime is worth little; a supervisor cannot check it and a
later reviewer cannot reconstruct it. A purpose **anchored to an exact span of an
exact source** — the instruction, the policy, the ticket that conferred the
authority — is checkable by anyone holding the source. That is precisely what the
claim layer already does for every other typed assertion, and the mandate is not
a special case.

*Candidate shape.* No new layer. A mandate is an ordinary span claim in the
existing claim form, retaining its profile-local predicate and projecting onto
the flat Federation-5D algebra like any other. What makes it a mandate is the
profile that supplies the vocabulary, not a privilege in the engine.

*Why this belongs here.* The alternative — a purpose held in a runtime's own
store — reproduces the failure the provenance spine exists to prevent: an
assertion with no source, no offsets and no way to reconstruct what was actually
authorised.

---

## V2 · A trajectory is a composition, and composition is what the concept layer does

An agent's action sequence is a sequence ordered in time, which is already one of
the shapes the concept layer composes: a set of atoms ordered in time becomes a
**process**. A trajectory is a process concept whose grounding atoms are the
recorded actions.

That framing carries two properties the oversight problem needs, and neither is
new work:

- **Many-to-many grounding runs both directions.** Which actions support this
  reading of what the agent was doing, and which readings does this action feed?
  The second direction is the one a reviewer actually needs and the one an action
  log cannot answer.
- **Concepts are a separate, regenerable layer.** A trajectory reading can be
  recomputed as understanding improves without touching the recorded actions
  beneath it. Provenance and claims never silently move or merge; the
  interpretation above them may.

*Candidate shape.* A trajectory profile over the existing process-composition
grammar. Whether the shipped grammars suffice or the richer process grammar
listed as *Designed* is required is an open question, and should be settled by
running a corpus rather than by argument.

*Boundary.* The engine composes the trajectory and grounds it. It does **not**
decide whether the trajectory diverged from the mandate — that is a reasoning
judgement, made through the interop contract by a consumer that owns it. The
engine holds the evidence on both sides and refuses the verdict.

---

## V3 · Control constituents are an nD system

Oversight is commonly decomposed into observability, intervenability,
comprehensibility, authority and timeliness — and the decomposition matters
because oversight can be formally present while one constituent is at zero,
which makes it functionally absent.

Those five are a typed, contextual coordinate system, which is exactly what nD
systems are for: *"users can add a narrow mathematical, scientific, or other
contextual system through declarative configuration without changing the
engine."*

*Candidate shape.* A registered, namespaced, versioned nD system — five axes,
declarative configuration, no engine change. Claims carry assignments in it the
same way they carry any other contextual scope.

*What the engine does not supply.* The **values**. Comprehensibility in
particular is a property of a person, not of a graph, and no configuration can
compute it. The engine provides the coordinate system and stores what a consumer
assigns; a consumer that assigns nothing gets nothing, and an axis left unset
must read as unset rather than as satisfied.

---

## The boundary, restated

Under a topical problem the pull toward scope creep is strongest, so the line is
worth restating in the terms the README already uses. Governance, priority
resolution and authoritative world construction are **outside** this engine.
Concretely, for this slice:

| Belongs here | Does not |
|---|---|
| the mandate as a span claim | whether the mandate was satisfied |
| the trajectory as a grounded composition | whether the trajectory diverged |
| the control-constituent coordinate system | the values on its axes, and what a zero means |
| what a source says about authority | who holds it, and whether they may act |

No domain is privileged by any of this. Agent oversight is a subject area like
any other: its vocabulary arrives in a profile, its concepts are discovered from
the corpus, and the core carries no oversight literal. The test guarding the core
against domain leakage applies unchanged and should be expected to catch any
drift here first.

---

## Sequencing

| Step | Item | Reach |
|---|---|---|
| 1 | V3 | declarative nD registration; no engine change |
| 2 | V1 | a profile supplying the mandate vocabulary; claim layer unchanged |
| 3 | V2 | trajectory profile over process composition; may surface a grammar gap |

## Gates

- the domain-leakage test stays green — no oversight vocabulary in the core;
- `tests/test_no_network.py` unaffected — nothing here reaches a network;
- every mandate and trajectory claim carries source, version and exact offsets,
  and the invariants that prevent fabrication apply unchanged;
- for V2, convergence rather than raw count is the signal: a trajectory profile
  whose new-concept rate does not decay is producing noise, and should be
  reported as such rather than shipped.
