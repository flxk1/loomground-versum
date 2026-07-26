# ADR-001: The Versum as a domain-general knowledge-graph framework

> **Historical status note (2026-07-19):** the domain-general decision remains accepted,
> but its 5D description and action-item status are superseded by
> `docs/reference/specification.md`, which is the normative source for current
> implementation status. Federation-5D is the five-value edge algebra; profile claim-form
> vocabularies project into it.

**Status:** Proposed
**Date:** 2026-07-17
**Deciders:** product owner; automated architecture review

## Context

The KG began as "Digital Law Sources" and its semantic vocabulary was ported from
Idea6's `nd_eu_law` (10 deontic predicates, EU-law principles, judicial canons, CELEX
instrument ranks). That was a coincidence of the first corpus — the framework must be
**open to any knowledge domain** (science, music-industry, history, …), with law as
merely profile #1.

Forces at play:
- The **rigor** of the 5D layer comes from *closed* vocabularies (fixed-length,
  comparable fingerprints). Genericity must not dissolve that into free text.
- The **many-to-many law** (PDF → n models, model → n PDFs) and the provenance floor
  are already domain-neutral — no law in them.
- Only two things are actually law-specific: the **axis vocabularies** (predicate /
  modality / principle / canon / inference-rule *values*, and the surface markers) and
  the **URN namespace** (`urn:dls:`). Everything else is universal.
- Idea6 gives the **design + the law catalogue values** but no runnable pipeline
  (only `catalogues.py` + a `circle.toml` schema parser exist on disk); the pipeline
  must be built.

## Decision

Split the system into a **universal framework** and **pluggable domain profiles**.

- **Universal framework (`src/versum/`, law-free):** the *form* — polarity (D/N) and the
  four-axis skeleton (logical-form, modality, quantification+rank, purpose+inference);
  the three-level graph model (Source 1:1← Claim n:m← Concept); the provenance spine;
  the per-document 5D+nD fingerprint; the read/write router; the sync contract. None of
  this names a legal concept.
- **Domain profile (a `Profile` object):** the *vocabulary* — the closed catalogue
  values for each axis, the surface-marker tables (per language), the instrument-rank
  ladder, and the **URN namespace**. `law-eu` ports Idea6; `generic` supplies a small
  domain-neutral catalogue and exists to prove the framework is not law-bound.

Framework code **never hardcodes a catalogue value**; it always asks the active
profile (`profile.is_valid(axis, value)`, `profile.markers`, `profile.namespace`). The
URN becomes `urn:<namespace>:<class>:<id>` where `<namespace>` is corpus/profile config
(`dls` for the law corpus); the framework treats the URN as an opaque key.

## Options Considered

### Option A: Universal framework + pluggable profiles *(chosen)*
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium — one indirection (the Profile) |
| Cost | Low — profiles are data, not code |
| Scalability | High — a new domain = a new profile, zero framework change |
| Team familiarity | High — mirrors Idea6's "circle" = domain-instance idea |

**Pros:** keeps the closed-vocabulary rigor *per domain*; law and non-law corpora
coexist in one engine; new domains are cheap; matches the Circleversum model.
**Cons:** requires disciplined dependency-inversion (no law leaks into framework);
cross-domain concept comparison only within shared axis *structure*, not values.

### Option B: Law-specific KG now, generalize later
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low now, High later |
| Cost | Low now |
| Scalability | Poor — law bakes into schemas, extractor, URNs |
| Team familiarity | High |

**Pros:** fastest to a working law KG.
**Cons:** contradicts the stated goal; every law assumption (deontic axes, CELEX,
`urn:dls`) becomes a later migration. Rejected.

### Option C: Fully generic, open vocabularies (no closed catalogues)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Cost | Low |
| Scalability | High |
| Team familiarity | Medium |

**Pros:** trivially domain-open.
**Cons:** destroys the 5D payoff — without closed vocabularies the fingerprint is not
fixed-length or comparable, and axis validity can't be checked. Rejected: openness must
be *per-profile closed*, not globally open.

## Trade-off Analysis

The real tension is **rigor vs openness**. Option C buys openness by discarding the
closed-vocabulary property that makes the 5D fingerprint comparable and checkable.
Option A keeps rigor by making the closure *per domain*: each profile is V1-closed, so
within a corpus fingerprints stay fixed-length and axis-validated, while a new domain
just supplies its own closed set. The cost — strict dependency inversion so no legal
term leaks into framework code — is a discipline cost, enforceable by a test that
imports `src/versum/` with only the `generic` profile loaded and asserts nothing law-shaped
appears. That test is cheap; the openness is permanent. Option A wins.

## Consequences

- **Easier:** adding a domain (music-law, AI-safety, a science corpus) = author a
  `Profile`; the extractor, graph, fingerprint, router, and sync are unchanged.
- **Easier:** law and non-law corpora share one queryable engine and one sync contract.
- **Harder:** must hold the line on dependency inversion — framework imports profiles,
  never the reverse; enforced by a `generic`-only import test.
- **Harder:** concepts are comparable across domains only through shared axis
  *structure* (`rhymes_with`), not shared values — which is correct (a legal
  "obligation" and a scientific "necessity" shouldn't unify by string).
- **Revisit:** the `generic` profile's starter vocabulary (V0) will need real use
  before it's trustworthy; treat it as provisional and widen only via the same
  curator-approval gate Idea6 uses (>5 uses + worked example + κ ≥ 0.8).

## Current status

The original action items have been implemented or superseded. Current implementation
status is documented in the [specification](../reference/specification.md); remaining
evidence gates are tracked in the [evidence ledger](../reference/evidence.md).
