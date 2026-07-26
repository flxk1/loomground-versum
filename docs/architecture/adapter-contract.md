# Model adapter contract

The engine is model-agnostic. It ships no model, names no provider, and runs its whole
default path with no model at all. Where a model is genuinely useful — resolving an
ambiguous identity, typing a span into the closed vocabulary, merging two phrasings of the
same concept, classifying a document's domain — the engine invites one in through a small
interface, and requires it to behave. This document is that contract. Adapters implement
it and live **outside** the `versum` package (an optional extra such as `versum[ollama]`,
or a companion repository), so the engine stays universal.

## The interface

An adapter provides callables for the grounded tasks the engine names in
`src/versum/model.py` — `resolve`, `type_span`, `judge_merge`, `classify_domain`. Each takes a
task context and returns a validated JSON object. The engine never imports the adapter; it
is handed the callable (as the `resolver` / `judge` argument) at the call site.

## The decoding policy — deterministic and constrained

Grounded tasks are classification into a closed set, not free generation, so they must be
called deterministically and constrained to that set. The engine enforces this in
`validate_decoding`, which an adapter must call before every grounded request:

- **Temperature 0.** Greedy decoding, plus a fixed seed, for reproducibility. Temperature
  is the weakest guarantee — it makes a wrong answer unlikely, not impossible — so it is
  necessary but never sufficient.
- **Constrained output format.** The response must be JSON conforming to a schema (the
  literal `"json"`, or an explicit JSON-schema object), so the model *cannot* emit a value
  outside the closed vocabulary. This is the strong guarantee.
- **Verification at the call site.** The returned value is checked against the closed
  catalogue and the invariants, and rejected or retried on any mismatch — regardless of
  how the model was configured. This is the backstop.

A config that ships a non-zero temperature on a grounded task fails `validate_decoding`
rather than silently degrading the graph; a test in the engine guards the policy itself.

## Configuration

The decoding settings are the adapter's config, not the engine's. JSON is a fine home:

```json
{
  "backend": "ollama",
  "endpoint": "http://localhost:11434",
  "tasks": {
    "resolve":         { "model": "qwen2.5:7b", "temperature": 0, "top_p": 1, "seed": 7, "format": "json" },
    "type_span":       { "model": "qwen2.5:7b", "temperature": 0, "top_p": 1, "seed": 7, "format": "json" },
    "judge_merge":     { "model": "phi3",       "temperature": 0, "top_p": 1, "seed": 7, "format": "json" },
    "classify_domain": { "model": "phi3",       "temperature": 0, "top_p": 1, "seed": 7, "format": "json" }
  }
}
```

The model names and endpoint above are one user's choice, not the engine's. Swap them for
any backend — a local model, an OpenAI-compatible server, a hosted API — and the contract
is unchanged. The engine reads none of this; it sees only the validated JSON the adapter
returns.

## What runs without an adapter

Everything on the default path. With no adapter wired, identity falls back to
deterministic patterns, concepts are the raw definition-seeded candidates, and no domain
classification runs. The adapter only upgrades the escalation rungs; it is never required
for the engine to work.
