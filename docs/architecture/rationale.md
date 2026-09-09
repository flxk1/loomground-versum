# Rationale and design principles

Text moved verbatim from the README (2026-09-09); the README keeps the interface, this file keeps the rationale.

> The normative contracts are in the [specification](../reference/specification.md);
> current verification and limitations are in the [evidence ledger](../reference/evidence.md).

Versum turns a folder of documents into a knowledge graph. You point it at a
directory, and it reads each file into span-anchored, typed atoms, then composes those
atoms into the recurring mental models the collection is really about. It is a general
engine: nothing about it is tied to a subject area. The examples in this document happen
to use European data-protection law because that was the first corpus to hand, but the
engine privileges no domain — the vocabulary for any field is supplied by a swappable
profile, and the concepts a corpus contains are discovered from the corpus itself.

The design goal is a graph you can trust. Every claim the engine records is anchored to
an exact span of an exact source, drawn from a closed vocabulary, and checked by
invariants — so the base layer cannot fabricate. Language models are used, when they are
used at all, on rails: they read and compose within the constraints the deterministic
layer sets, and their output is verified before it is stored. Most work needs no model.

## Capability status

- **Operational:** provenance reuse, deterministic identity, span claims, Federation-5D
  projection, profile-local claim form, typed nD systems and assignments, concepts,
  many-to-many grounding, universal system adapters, Loomground semantic projection,
  hybrid retrieval, and incremental sync.
- **Experimental:** concept normalization, automatic canon convergence, typed pair
  compositions, and optional model deepening.
- **Designed:** richer process/conditional/relation/diff composition grammars and broader
  custom nD extraction adapters.
- **Outside Versum:** governance, priority resolution, and authoritative world construction.

## What it builds

The graph begins with a **provenance spine** of canonical sources and versions. The **claim
layer** binds each typed assertion to one source and exact character offsets. Claims retain
their profile-local form and project their predicate onto the flat Federation-5D edge algebra.
Their typed nD assignments record contextual scope. Provenance and claims never silently
move or merge.

The **concept layer** sits on top. A mental model is not a single atom but a
*composition* of them — a cluster of atoms about one term becomes an entity concept, a
sequence ordered in time becomes a process, a set of conditions becomes a scenario. The
engine proposes these compositions with deterministic grammars and records them as a
separate, regenerable layer linked back to the atoms that ground them. A concept can be
grounded by many documents, and a document can feed many concepts; that many-to-many
grounding is what lets you ask, in both directions, which models a source supports and
which sources support a model.

Concepts are expected to *converge*. Within a domain there is a bounded canon of mental
models, so as documents accumulate each new one mostly re-uses concepts already seen and
adds only a little. A healthy run shows that new-concept rate decaying toward zero; a run
that never settles is producing noise, not knowledge. Convergence, not raw count, is the
signal that the graph is good.

## Design principles

The engine follows a few commitments that are worth stating plainly, because they shape
every part of it.

*Deterministic floor, model on the rails.* Identity, deduplication, span extraction,
axis validation, and the invariants are plain Python and run with no model. Where reading
genuinely needs judgement — a messy citation, a concept that must be merged across
phrasings or languages — a model is invited in, but only to choose from the closed
vocabularies and grounded in a given span, and its output is verified before it counts.
The model never runs on the happy path and never has the last word without a check.

*Local-first and model-agnostic.* The engine ships no model and names no provider. It
exposes a small interface — a resolver for ambiguous identity, a judge for concept
hygiene — and any backend clicks into it: a local model, an OpenAI-compatible server, a
hosted API, or nothing. See the [model boundary](../architecture/model-boundary.md) for the
exact boundary. The optional `versum.integrations.ollama` adapters are the one exception to
"no network": wiring one in makes real HTTP calls to a local Ollama server. No shipped skill
does this by default; it is available only if you instantiate it yourself. The engine's own
no-network test (`tests/test_no_network.py`) deliberately excludes `integrations/` for this
reason.

*Domain is neutral and per-document.* A folder is just a bag of files and may hold many
subject areas at once; a single document may touch more than one. Domain is therefore a
property of the document, not the folder, and the engine hard-codes no list of domains.
Vocabularies live in profiles (`generic` by default; add your own), gold sets and corpora
are external user data, and any domain label a concept carries is applied by a universal
rule, never baked into the core. A test guards the core against domain leakage.

*Flat Federation-5D, extensible nD.* Every local predicate projects onto one of five stable
edge-reasoning dimensions: structural, causal, intentional, temporal, or relational. Local
predicates retain their finer meaning. Context lives in typed, namespaced and versioned nD
systems; users can add a narrow mathematical, scientific, or other contextual system through
declarative configuration without changing the engine.


## Layout

The `src/versum/` package is the domain-neutral engine. Profiles live in `src/versum/profiles/`;
`generic` is the neutral default. The normative contracts are in the
[specification](../reference/specification.md), current verification and limitations are in
the [evidence ledger](../reference/evidence.md), and the architectural rationale begins with
[ADR-001](../decisions/001-domain-general.md).

## Status

Versum is alpha software: its file formats and command-line interface may still change.
The provenance layer, folder indexer, guarded write path, and deterministic curation loop are
built and tested. The model-on-rails reader, shared per-domain canon, and scenario layer remain
open work, tracked against the normative contracts in the
[specification](../reference/specification.md). See the [evidence ledger](../reference/evidence.md)
for verified coverage and explicit limitations. Run the suite with `python -m pytest tests/`.

## Authorship

This work is authored by **Loomground Contributors** and was assisted by Claude and Codex. Claude
and Codex are acknowledged as tools, not authors or co-authors.
