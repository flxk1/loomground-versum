# ADR-005: LLM deepening at the index step (deterministic-first, model-as-escalation)

**Status:** Accepted (harness + contract; model implementation device-side)
**Date:** 2026-07-18
**Deciders:** engine owner

## Context

The deterministic coordinate layer (M=1, and M>1 pairs) captures *shallow* mental models: a
claim's signature + subject, and co-occurring pairs. It leaves detail on the table — the
internal relations of a claim (agent / patient / condition / consequence), multi-step
structure, and the ~80% of claims that are *unclustered* (no corpus-salient subject) because a
surface heuristic can't name their model. A local LLM could deepen exactly those, extracting
richer structure the deterministic pass cannot. The user has local models (Qwen/Phi via
Ollama).

Constraints (unchanged): the engine core stays deterministic and model-free; any model runs
**device-side** and **model-agnostic** (an injected adapter, like the retrieval Dense layer);
the escalation is **bounded** (a budget — LLM calls are the expensive step) and **additive**
(deepenings are a separate artifact, never a silent mutation of the deterministic canon).

## Decision

Add `versum/deepen.py`: a deterministic **escalation harness** plus a `Deepener` adapter
contract.

- **Candidate selection is deterministic and bounded.** `escalation_candidates(...)` ranks and
  caps which items get an (expensive) LLM call — by policy: `unclustered` residue first (the
  claims the deterministic pass could not model), then `dense-unit` claims (rich context),
  under a `budget` (max calls). No model is involved in *choosing*.
- **The model call is an injected adapter.** `Deepener.deepen(text, context) -> structured`
  returns richer structure (relations, sub-claims, a proposed mental-model label) as validated
  JSON. `NullDeepener` (default) does nothing; `EchoDeepener` is a test stub; the real one is
  `versum/integrations/ollama/deepener.py` (device-side Qwen/Phi). Core never imports a model.
- **Output is additive.** Deepenings are written to a separate `deepenings.jsonl` keyed on
  `canonical_urn` + `item_id`; a later, opt-in merge can promote them into the graph. The
  deterministic canon is untouched.

## Options Considered

### A: LLM extracts everything (replace the deterministic pass)
Rejected: non-deterministic, unbounded cost over 392k claims, and loses the auditable
deterministic floor the whole engine is built on.

### B: No LLM (deterministic only)
The status quo. Leaves the residue and intra-claim structure unmodeled. This is the fallback
when no model is available — the engine still runs.

### C: Deterministic selection + bounded LLM escalation, additive output (CHOSEN)
The model deepens only where the deterministic pass is weakest, under a budget, without
touching the deterministic artifacts. Matches the write-guard / curation escalation ladder and
the retrieval Dense adapter — one consistent "deterministic-first, model-as-escalation" story.

## Trade-off Analysis

The value is concentrated in the residue and in intra-claim structure, exactly where a surface
heuristic is blind — so spending bounded LLM budget there is high-leverage. Keeping selection
deterministic makes the run reproducible and the cost predictable; keeping output additive
keeps it reversible and keeps the deterministic canon as the auditable floor. The cost is a
second artifact and a merge step, and quality now depends on the chosen local model — acceptable
because it's opt-in and bounded.

## Consequences

- **Easier:** deeper models where they matter; a clean seam for the user's local model; the
  residue stops being a dead end.
- **Harder:** output quality depends on the local model; a merge policy is needed to promote
  deepenings into the graph (future); prompt/schema versioning matters for reproducibility.
- **Revisit:** the selection policy and budget after seeing real residue; whether deepenings
  feed M>1 composition; a verification pass (a second model or deterministic checks) over LLM
  output before promotion.

## Action Items
1. [x] `versum/deepen.py`: deterministic `escalation_candidates` + `Deepener` protocol + Null/Echo + additive `deepenings.jsonl` writer.
2. [x] `versum/integrations/ollama/deepener.py`: device-side Qwen/Phi adapter (not run in core).
3. [ ] (device) run against real residue; design the promote-to-graph merge + a verification pass.
