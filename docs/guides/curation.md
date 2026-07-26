# Runbook — Coordinate-Identity Curation (the mental-model / concept layer)

This turns the **392k already-extracted claims** in your KG into the **concept layer**:
every claim gets a content-derived **5D+nD coordinate**; claims that share a coordinate —
across sources and across domains — name the **same concept**. The concept layer emerges by
*convergence*, not by hand. It fills the currently-empty `concepts.csv` +
`semantic_edges.csv` in each `by-domain/<domain>/` and writes a global `canon.json` (the
domain canon) and `convergence.json` (the mint curve) at the KG root.

It is **CPU-light**: it reads claim rows already on disk — **no PDF parsing, no network, no
model**. Safe to run as a long Terminal session. **Resumable** and **parallel**: a finished
domain is skipped on re-run unless its `claims.csv` changed. Nothing is deleted or
overwritten except the two concept tables (previously empty) and the two reports.

## What you got

```
loomground-curation/
├── loomground-versum/        # the full engine (canon.py included), 156 tests green
├── curate_full.py            # the Terminal runner
└── RUNBOOK-curation.md       # this file
```

## Run it

```bash
cd /path/to/loomground-curation

# point at your existing KG config (the one migrate_full.py used):
python3 curate_full.py --config "/Users/…/Knowledge/Loomground Sources/06_Graph/versum/loomground-kg.config.json"
```

Config + engine resolution (device-neutral — no machine path lives in the code):

- **config**: `--config <path>`  ›  `$LOOMGROUND_KG_CONFIG`  ›  `./loomground-kg.config.json`
- **engine**: `$VERSUM_ENGINE`  ›  `./loomground-versum`

So from inside the extracted folder, `--config …` is the only argument you need; it finds
`./loomground-versum` on its own.

### Options

```
--workers N     parallel domain jobs        (default: CPU count − 1)
--m-max N       coordinate composition depth (default: 1 — single-claim coordinates)
--force         recurate every domain, ignoring the resume markers
```

## What it prints

Live per-domain lines, then a summary you can read for quality:

- top concepts by **cross-source support** (`n_sources` / `n_claims`) with their domains,
- the **convergence tail** (distinct coordinates after all sources; how many the last source
  still minted — a small number means the canon is saturating),
- **canon size by domain**,
- where it wrote everything.

## What it writes

| Path | Meaning |
|---|---|
| `by-domain/<domain>/concepts.csv` | concept rows, canonical-keyed (same schema as materialize) |
| `by-domain/<domain>/semantic_edges.csv` | one `grounds` edge per claim → its concept |
| `by-domain/<domain>/canon.partial.json` | that domain's mergeable partial (resume + reduce) |
| `<kg_root>/canon.json` | the global domain canon: concepts with support + domains |
| `<kg_root>/convergence.json` | the mint curve across the whole corpus |
| `<kg_root>/_curate/_done_domains.json` | resume markers (domain → claims signature) |

Re-running is a true no-op for unchanged domains, and the concept tables are a
**deterministic** function of the claims (byte-identical on a `--force` re-run).

## What to expect (validated on real claims, not just synthetic)

I ran this on a sample of your real materialized domains (6 domains, ~3,470 claims). Honest
findings so you are not surprised:

- **Coverage is partial.** At M=1 only the claims with a *corpus-salient subject* (a term
  quoted somewhere, or recurring across ≥2 sources) get a concept; on the 6-domain sample
  **~20% of claims clustered**, the rest are reported as an **unclustered residue** (see
  `clustered_rate` / `n_unclustered`). That residue is deliberate — a claim with no salient
  subject is not forced into a meaningless bucket. Expect the rate to differ on the full
  corpus (more sources → more terms recur → more clustering).
- **Two limits are UPSTREAM of this layer, not fixable here:**
  1. The **"lost spaces" PDF-extraction artifact** (pdfplumber) mangles some terms
     (`designmitdentechnischen…`) and fragments one concept across coordinates
     (`digitalen-produkts` / `digitale-produkt` / `digitalen-produkten` = one "digital
     product"). A junk-glob filter drops the worst globs, but the fragmentation from mangled
     spacing + German declension remains. **Fixing extraction spacing first is the highest-
     leverage improvement** — it poisons every downstream layer.
  2. **Morphology.** German declensions split one concept into several coordinates. Collapsing
     them needs light lemmatization, which is a deliberate (determinism/neutrality) decision —
     not yet added.
- **What works well:** deterministic, resumable, correct canonical-keyed output; real
  convergence exists (on the sample, ~100 concepts recurred across ≥2 sources, e.g.
  `member-states`, `unidroit-principles`, `european-union`); cross-domain merge is automatic
  when a coordinate genuinely recurs across domains.

Read `canon.json` after the run: `clustered_rate`, `n_unclustered`, and the top `concepts`
tell you immediately whether the canon is meaningful for your corpus or whether the extraction
fix should come first.

## How identity works (M = 1)

- **coordinate** = the claim's closed-axis signature (`polarity`, `predicate`, `modality`,
  `quantification` — what the extractor already stamped) **+ a `key_term`** parsed from the
  grounding text (a quoted term, else a salient capitalized phrase, else the most salient
  content token).
- **concept_id** = a bare slug that is a *projection* of the coordinate onto the identity
  axes (default `polarity + predicate + key_term`), e.g. `m-n-imposes-controller`. It owns
  its identity — never a source URN — and is content-derived, so the same coordinate from
  two different works converges to one concept.
- **M-max** is the composition depth. `1` = single-claim coordinates. Deeper composition
  (co-occurring coordinates within a source forming higher-order models) is a designed
  extension point, not yet minted — bump `--m-max` only once that layer ships.

## After it runs

The cockpit skill (`kg_query.py`) and any KG reader now see a populated concept layer in the
same canonical-keyed schema as the claims. `canon.json` is the domain canon (the bounded
ceiling of concepts) and `convergence.json` shows it saturating.

To re-curate only domains whose claims changed since last time: just run it again (no
`--force`). To rebuild everything: add `--force`.
