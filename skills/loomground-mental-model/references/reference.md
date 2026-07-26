# loomground-mental-model - reference

## How it runs — the deterministic engine, model on the rails

The work is done by the installed `versum` engine (`python -m versum ...`), the same
deterministic core the write path uses. Per Versum's own contract: identity, span
extraction, composition grammars, and the invariants are plain Python and need **no model
call**; a model is invited in only where reading needs judgement (a concept that must merge
across phrasings or languages), only to choose from the closed vocabulary grounded in a
given span, and its output is **verified before it is stored**. The model never runs on the
happy path and never has the last word without a check. It is **local-first and
model-agnostic** — the engine ships no model and names no provider; a local backend (Ollama)
clicks in first, a hosted one only on the user's opt-in.

This skill is a thin wrapper: it knows which engine verb each stage calls and how to read the
report. It does not re-implement the engine.

## The pipeline — stages mapped to real engine verbs

| Stage | What it does | Engine verb |
|---|---|---|
| **SCAN / INGEST** | read text, structured data, or a document into span-anchored typed atoms | `versum ingest <item>` · `versum capture <folder>` · `versum index <folder>` |
| **COMPOSE / MATCH** | cluster atoms into typed concepts and match against the existing canon | `versum suggest <folder>` → `versum confirm <folder>` |
| **CANON / DEEPEN** | converge new concepts into the bounded domain canon; optional model deepening for a fuller entity twin | `versum canon-domain <folder>` |
| **QUERY** | which mental models a source supports, which sources ground a model, hybrid retrieval | `versum models <folder> <urn>` · `versum sources <folder> <concept_id>` · `versum search --config <c> --q "…"` |
| **PROJECT** | project the ConceptGraph onto the Federation-5D edge algebra and into an output modality | engine projection (`adapt` / materialize / morph) |
| **PERSIST / REGISTER** | write the model + provenance into the graph | hand off to `loomground-knowledge-write` (never a direct write here) |

**Intent-driven projection (the Translator role).** Detect what the user actually asked —
how / who / when / risk / obligations / teach — and pick the projection that answers *that*:
a checklist, timeline, diagram, storyboard, table, narrative, slides, schema/SQL, or audio.
The projection is a **regenerable view** of the model, never a new source of truth.

## Inputs

- **content** — text, structured data (JSON/CSV/dicts), a conversation, or a local document.
- **target** — the Versum workspace (`.versum/` store) the model belongs to. Default: the
  active Knowledge workspace.
- **profile** — the domain profile (`generic` by default) that supplies the vocabulary; the
  engine hard-codes no domain.
- **projection** — the requested output modality (optional; inferred from intent if unstated).
- **effort** — deterministic / local-first / cloud, per the user's owned effort policy (the
  same dial as `loomground-organise`). Default local-first cascade; cloud is opt-in.

## Steps

1. **Scan** the content into atoms (`ingest` / `capture`), keeping originals as RAG items —
   never discard the source.
2. **Compose** atoms into a ConceptGraph (`suggest` → `confirm`); match against the existing
   canon so the model re-uses concepts already seen rather than minting noise.
3. **Check convergence.** A healthy model mostly re-uses concepts; a run whose new-concept
   rate never decays is producing noise, not knowledge — say so and stop rather than emit it.
4. **Deepen only if asked** (entity twins): `canon-domain`, escalating to a local model on
   the effort ladder, cloud only on opt-in.
5. **Project** to the intended modality; label it a view of the model with its grounding
   intact.
6. **Persist only through the one door.** If the user wants the model kept, hand off to
   `loomground-knowledge-write` (identity, dedup, sidecar, index) with human confirmation;
   this hub never writes to the graph directly.
7. **Report** the concept count, convergence signal, grounding coverage, and unresolved
   questions; expose uncertainty and competence limits rather than smoothing them over.

## Guardrails

- **Grounded or not stated.** Every concept traces to an exact span of an exact source; the
  base layer cannot fabricate, and neither may a projection.
- **Projection is regenerable, not authoritative.** A view of a model never becomes a new
  source of truth; re-project freely, but the graph is the record.
- **Writes are human-gated and single-door.** No direct graph writes here — everything
  persistable goes through `loomground-knowledge-write`.
- **Domain-neutral.** Vocabulary comes from the profile, never hard-coded in this skill.
- **Local-first, no in-session fetching.** Prefer the local model; never pull a binary over
  the network mid-session.
- **Honest status.** Federation-5D projection, semantic projection, and hybrid retrieval are
  operational; concept normalization, typed-pair compositions, and model deepening are
  experimental; richer render grammars (full multi-format output) are designed, not done —
  do not claim an output format the engine cannot yet produce.

## Relationship to the other Versum hubs

- **loomground-knowledge-write** — the one write path; this hub calls it to persist, never
  bypasses it.
- **loomground-organise** — places a captured document by its concept-neighbours; it consumes
  the concepts this hub produces.
- **loomground-kg** — the read-only query cockpit; "chat with the knowledge graph" lives
  there, over the models this hub builds.

