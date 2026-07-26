---
name: loomground-curate
description: Run Versum's coordinate-identity curation to mint the concept / mental-model layer of the knowledge graph, for the whole KG or one domain folder. Use when the user wants to curate the concept layer, build the domain canon, check a domain's concept coverage or convergence, or upgrade KG chat multi-hop from claim/source level to concept level. The canon run IS the write - it materializes the concept tables in place (previously empty tables only; claims and registry untouched) - so confirm with the human BEFORE running. Deterministic and local - no model, no network. Triggers - "curate the concept layer", "run coordinate curation", "mint the concepts", "build the domain canon", "has this domain converged", "why are there no concepts in the KG".
---

# loomground-curate — coordinate-identity curation

Mint the concept layer: every claim's closed-axis signature (polarity, predicate,
modality, quantification) plus a key term parsed from its grounding text becomes a
content-derived **coordinate**. Claims from different sources that share a coordinate
name the SAME concept — the concept layer emerges by convergence, never hand-authored,
and a `concept_id` is a function of claim content, never of its source.

## Step 1 — Confirm scope with the human BEFORE running

The run is the write. `versum canon` materializes, in place: `concepts.csv`,
`semantic_edges.csv`, `composition_edges.csv` and `canon.partial.json` in every
`by-domain/<domain>/` folder, plus `canon.json` and `convergence.json` at the KG root.
It only ever (over)writes these concept tables — `claims.csv` and the registry are
never touched — but get explicit confirmation of the target (whole KG or one domain)
before running, not after:

```bash
python3 -m versum canon --config CONFIG.json [--m-max 1]     # whole KG
python3 -m versum canon-domain FOLDER [--m-max 1]            # one by-domain folder
```

`--m-max` is composition depth; leave at 1 (depth-1 coordinates) — deeper composition
is a documented extension point, not yet minted. Check first whether a current canon
already exists (`canon.json` at the KG root, newer than the claims files): curation is
deterministic, so re-running over unchanged claims reproduces the same canon.

## Step 2 — Read the canon back to the human

- **Concepts minted** — one per coordinate, each with support: how many claims, how
  many distinct sources, which domains.
- **Convergence** — distinct coordinates vs sources processed. Flattening means the
  domain approaches its canon ceiling (new sources stop minting new coordinates);
  still climbing means more sources will still grow the canon. Say which.
- **Weakly-supported concepts** — support from a single source is a coordinate, not
  yet corroborated; flag rather than hide.

## Step 3 — Verify on the tables, not the CLI

`versum sources FOLDER CID` and `versum models` read `FOLDER/.versum/` (watched-folder
state) and return `[]` against materialized by-domain folders — do NOT use them to
verify curation. Verify directly on what was written:

- `canon.json` at the KG root reports `n_concepts > 0`.
- Concept→sources multi-hop: in a by-domain folder, join `semantic_edges.csv`
  (`edge_type == "grounds"`, `dst_id == <concept_id>`) to `claims.csv` on
  `item_id`, and read the distinct `source_urn`s.

After a successful run, `loomground-kg` status reads concept counts from
`canon.json`, and `loomground-kg-chat` multi-hop answers at concept level.

## Boundaries

- Deterministic, local-first: no model calls, no network, no invented concepts — the
  engine hardcodes only language-generic label hygiene; domains and predicates are data.
- This skill does not scan or project content (`loomground-mental-model`), does not file
  documents (`loomground-organise`), and does not write claims or sources
  (`loomground-knowledge-write`).
