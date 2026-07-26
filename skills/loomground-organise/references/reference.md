# loomground-organise - reference

## How it runs — deterministic helpers plus model judgement

Two deterministic Python scripts do the mechanical work:

- `python scripts/organise.py list --review <review_dir>` — show waiting items from
  their `*.metadata.json` provenance sidecars (URN, year, provenance level).
- `python scripts/organise.py suggest --store <kg_root> --concepts <c1,c2,...>` — rank
  candidate domains and nearest sources by rarity-weighted (IDF) concept overlap.

The model reads the ranked evidence and the document, then drafts the placement call.
The effort ladder (regex → local LLM → cloud LLM) is configurable via policy.

## Inputs

- **review_dir** — the workspace review queue (data side, under `Knowledge/`).
- **kg_root** — the by-domain store to rank against.
- **document** — the item to place (so the model can read and weigh evidence).
- **config** (optional) — effort policy file (`organise.config.example.json`).

## What it returns

- **ranked_domains** — candidate domains with overlap scores and nearest sources.
- **recommended_tier** — which effort tier produced the suggestion (`regex`, `local-llm`, `cloud-llm`).
- **mint_rate** — proportion of new concepts (high = genuinely novel item).
- **confirmation_needed** — always true; never auto-files.

## Guardrails

- **Never auto-file.** Placement is a suggestion a human confirms.
- **Never invent a domain.** Domains come from the store, not from this skill.
- **Never write directly.** Every write is the `loomground-knowledge-write` path.
- **Trust evidence, not filler.** If shared concepts look like stopwords, say so and
  fall back to review.

## Pairing

After confirmation, hands off to `loomground-knowledge-write`. Reads concepts extracted
by the capture/sync pipeline.
