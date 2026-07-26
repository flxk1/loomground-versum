# Where Claude (an LLM) is needed — and where it isn't

Loomground Versum runs as a **deterministic Python pipeline**. The whole default path —
adding documents and building the graph — needs **no model call at all**. An LLM is an
*escalation*, wired on a ladder (a **local** model first, a hosted model only after),
used only for the few jobs that genuinely need judgement.

## Runs with zero LLM (pure Python)

- **Identity** — canonical URN from filename patterns (CELEX / arXiv / DOI) and PDF
  metadata (`versum/write.py`).
- **Dedup** — content hash + URN + title against the source registry.
- **Extraction** — segment into units, scan surface markers, stamp the closed 5D axes,
  span-anchor every claim (`versum/io/extract.py`).
- **Fingerprint** — the per-document 5D histogram + nD coordinates (`versum/identity/fingerprint.py`).
- **Concept seeding + linking** — definitions seed candidate concepts; mentions link
  claims; cross-source support is counted (`versum/concept/curate.py`).
- **Graph traversal + invariants** — the many-to-many law both ways; orphan / own-identity
  checks (`versum/store/graph.py`).
- **Persistence** — everything to `<folder>/.versum/`.

That is the guard, the index, and the curation *suggestions* — all deterministic.

## Where an LLM earns its place (ladder: local first, hosted only after)

1. **Ambiguous identity.** When a file has no CELEX/DOI/arXiv id and no usable metadata,
   the deterministic rung falls back to a path-slug. A model can read the first page and
   propose the real citation. Hook: the `resolver` argument in `resolve_identity`.
2. **Concept hygiene + merging.** The deterministic suggester over-produces (e.g.
   "purposes and", "request by electronic") and can't tell that the English "personal
   data" and the German "personenbezogene Daten" are the *same* concept. A model cleans
   labels, drops noise, and merges cross-lingual / synonymous concepts. This is the single
   highest-value use of an LLM in the system — it turns noisy candidates into a clean
   concept registry. Hook: a `judge` over `curate.suggest`'s output.
3. **Confirming the curation-only axes.** `principle`, `judicial_canon`, `inference_rule`,
   and `confidence` are deliberately left unspecified by the extractor. A model proposes
   them per claim for the curator to confirm.
4. **Editorial prose.** Newsletters, essays, presentations, design — the
   `loomground-editorial` render commands. Not part of the graph engine.

## The rule

Deterministic Python is the floor and the default; the LLM is opt-in escalation, never on
the happy path, and always local-model-first. If no model is wired, everything still runs
— you just get path-slug identities and raw (unmerged) concept candidates instead of
cleaned ones.
