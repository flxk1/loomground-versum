# Runbook — Re-extract (fixed spacing) then re-curate

The extractor now repairs the "lost spaces" artifact (merged words like
`derAnspruchaufHerstellung`) using per-line glyph-gap geometry (ADR-002). To get the fix into
your KG you re-extract the corpus, then rebuild the canon on the clean claims. Both steps are
config-driven, resumable, parallel, and read-only on your PDFs.

## Order matters

```
1) reextract_full.py   # re-parse every PDF with fixed spacing → regenerates by-domain/*/claims.csv
                       #   (this RESETS concepts.csv / semantic_edges.csv to empty)
2) curate_full.py      # rebuild the coordinate-identity canon on the clean claims
```

Do not run curation first — re-extraction overwrites the claim tables and clears the concept
tables by design.

## Install (one-time)

```bash
# from wherever the bundle landed (e.g. your Loomground folder):
tar -xzf loomground-curation.tar.gz
cd loomground-curation               # self-contained: bundles the FIXED engine as ./loomground-versum
```

Run the two steps below from inside this folder so they use the bundled fixed engine (they
resolve `./loomground-versum` automatically). This does not touch any other engine copy on
your machine.

## Run

```bash
cd /path/to/loomground-curation      # the extracted bundle (contains ./loomground-versum)

# 1) re-extract — CPU-heavy (PDF parsing), similar to the original migration (~90 min).
python3 reextract_full.py --config "/Users/…/06_Graph/versum/loomground-kg.config.json" --force

# 2) re-curate — CPU-light (reads claims), minutes.
python3 curate_full.py   --config "/Users/…/06_Graph/versum/loomground-kg.config.json" --force
```

Config resolves from `--config` › `$LOOMGROUND_KG_CONFIG` › `./loomground-kg.config.json`;
engine from `$VERSUM_ENGINE` › `./loomground-versum`. `--force` re-does everything; without it
each runner skips domains whose inputs are unchanged (resume). `--workers N` sets parallelism.

## What re-extraction writes

| Path | Meaning |
|---|---|
| `by-domain/<domain>/claims.csv` | regenerated claims, now with clean word spacing |
| `by-domain/<domain>/{concepts,semantic_edges}.csv` | reset to empty (curation refills) |
| `<kg_root>/_reextract_progress.json` / `_reextract_done.txt` | progress + resume markers |
| `<kg_root>/_reextract_errors.log` | any per-domain errors (never aborts the run) |

Provenance is unchanged: claims still key on the registry `canonical_urn` (reuse), corpus is
never modified.

## How the fix works (ADR-002, one paragraph)

A PDF inserts a space between two glyphs only when their horizontal gap exceeds a threshold;
justified/tight legal PDFs fall below it, so words merge. A single global threshold cannot win
(lowering it shatters loosely-tracked words). Instead each line's own gap distribution sets an
intra-word **baseline** (a low percentile of the line's glyph gaps) and a space is inserted at
every gap above `baseline + margin` — so tight-merged, loose-tracked, justified (uneven gaps),
two-column, and mixed-font lines are all handled, while single words and clean prose are left
untouched. Pure geometry; no dictionary, no model; deterministic. Truly zero-gap concatenation
(no geometric signal at all) is not recoverable this way and is left as-is rather than guessed.

## Per-domain profiles (the third input to concept quality)

A claim's coordinate is **axis-signature + key_term**, and the axis half (`predicate`,
`modality`, `polarity`) is stamped by the extraction **profile**. The original migration ran
*everything* under `law-eu`, so non-law domains (philosophy, CS, economics, …) were stamped
with legal deontic predicates they don't have — which corrupts **concept identity**, not just
claim text. So concept quality has three upstream inputs: extraction spacing (fixed here),
morphology/lemmatization (open), and **per-domain profiles**.

`reextract_full.py` now routes a profile **per domain**. In the config:

```json
"profile_id": "law-eu",
"domain_profiles": {
  "classic_philosophy": "generic",
  "computer_science_and_cybernetics": "generic",
  "economics_and_political_economy": "generic"
}
```

`domain_profiles` maps `domain` (or `library:domain`) → a registered profile, overriding the
default. Honest caveat: only `generic`, `law-eu`, `news` are registered today. `generic` is
neutral but **sparse** — on legal-style text it extracts few/no claims — so routing a domain
to `generic` is "less wrong" than `law-eu` only when that domain's text is genuinely non-legal.
Getting real signal from philosophy/CS/economics claims needs **authoring domain profiles**
(closed predicate/modality vocabularies per field); the routing here is the dial that makes
that possible, not a substitute for it. Leave `domain_profiles` empty to reproduce the current
single-profile behaviour.

## After both runs

Read `<kg_root>/canon.json`: `clustered_rate` should rise versus the pre-fix run (fewer claims
fragmented by mangled spacing), and the top `concepts` should show fewer junk / run-together
key_terms. Compare against the numbers in the curation runbook's "What to expect" section.
