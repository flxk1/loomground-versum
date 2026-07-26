# ADR-004: Hybrid matching / retrieval index

**Status:** Accepted
**Date:** 2026-07-18
**Deciders:** engine owner

## Context

5D+nD split reasoning (`universal_form`) from **retrieval** (Idea6, 2026-05-01): the coordinate
fingerprint is NOT the search index. To actually *find* claims/concepts — "obligations about
processors in the privacy domain", "concepts near this text" — the KG needs a retrieval layer:
facet filtering on the structured axes + lexical ranking on text + (optionally) dense semantic
similarity. It must be domain-neutral, deterministic where it can be, and must not require a
model to run (the dense model is device-side: the user's Qwen/Phi via Ollama, not reachable
from the engine's container).

## Decision

Add `versum/store/retrieve.py`: a hybrid index over the materialized KG.

- **Facet index** — exact-match postings on the structured fields (type, polarity, predicate,
  modality, quantification, domain, library, concept_id, depth m). Deterministic.
- **Sparse lexical (BM25)** — Okapi BM25 over claim text + concept labels/surface terms. Pure
  python, deterministic, no dependency.
- **Fusion query** — filter the candidate set by facets, rank by BM25, optionally re-rank by a
  dense score; return top-k with provenance (canonical_urn, concept_id, domain).
- **Dense layer = an injected adapter**, `Dense.embed(texts) -> vectors`. The real
  implementation is device-side and **model-agnostic** (Ollama Qwen/Phi); it is never called
  from core. A deterministic `HashingDense` fallback exercises the rerank path in tests, and
  `NullDense` (default) skips reranking. The engine ships the contract, not a model.

## Options Considered

### A: Lexical only (BM25 + facets)
Simple, deterministic, no model. Misses paraphrase/semantic matches. This is the always-on core.

### B: Dense only (embeddings)
Strong semantics, but non-deterministic across models, needs a model to run at all, and loses
exact facet precision. Rejected as the base layer.

### C: Hybrid — facets + BM25 always, dense as an optional injected reranker (CHOSEN)
Deterministic core runs everywhere; dense is a pluggable device-side adapter that improves
ranking when available. Matches the "deterministic-first, model-as-escalation" boundary the
rest of the engine uses (the write guard, curation).

## Trade-off Analysis

Keeping dense as an injected adapter is the crux: it preserves determinism and offline
operation of the core, keeps the engine model-agnostic (the user's local models plug in on the
device), and still allows semantic rerank where a model exists. BM25 + facets alone already
answer structured + keyword queries well; dense is upside, not a dependency.

## Consequences

- **Easier:** structured + keyword retrieval over the KG immediately; a clean seam for the
  local model to add semantic rerank on the device.
- **Harder:** two ranking signals to fuse (a normalization + weight `alpha`); index build/refresh
  over very large claim sets remains an explicit operator cost.
- **Revisit:** persistence format at full-corpus scale; whether concepts or claims are the
  default retrieval unit per query type; fusion weight tuning against judged queries.

## Implementation

`versum/store/retrieve.py` ships the document model, BM25 and facet postings,
fusion search, dense protocol, deterministic hashing/null adapters, persisted
index format, incremental update, and KG loader. The `versum search` CLI and
`tests/test_retrieve.py` cover facet precision, ranking, fusion, persistence,
incremental refresh, and determinism.
