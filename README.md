# loomground-versum

Span-grounded knowledge and evidence plane: indexes a folder of documents into a provenance-anchored graph of typed claims and concepts.

## Problem

Answers cite nothing; a claim cannot be traced to the sentence it came from. A graph where every claim keeps its span, searchable, model calls opt-in.

## Install

```bash
pip install -r requirements-dev.txt   # pinned loomground-governance + loomground-deontic
pip install .                         # installs the `versum` command
```

## Usage

```bash
versum index   <folder> --profile generic           # span-anchor, project 5D + nD
versum capture <folder> --profile generic           # idempotent admission + index
versum search  --config <live-index.json> --q "…"   # hybrid retrieval
versum coords  <store> <entry-id>                   # one entry's 5D+nD coordinates
versum cell    <store> --where sys.axis=value        # entries at an nD coordinate
```

## Example

```
in : versum index policy --profile law-eu        # policy/policy.txt: three sentences
     cut -d, -f5-8 policy/.versum/claims.csv
out: span_start,span_end,marker,text
     78,139,must not,The operator must not transfer personal data outside the EU.
     0,78,must,The operator must delete personal data within 30 days after the contract ends.
     139,187,may,The operator may retain invoices for ten years.
```

## Interface

| Layer | Surface |
| --- | --- |
| Storage | `<folder>/.versum/`: sources, span claims, fingerprints, concept registry, grounding edges, `nd/` manifests, `_events.jsonl`. Write doors: `capture`, `capture-file`, `versum.ingestion.DimensionedSubgraphSink` (`loomground.versum.dimensioned-subgraph/v1` envelopes, idempotent receipts) |
| Retrieval | `search` (BM25 + dense, facet filters) · `models <urn>` · `sources <concept-id>` · `changes --since <watermark>` |
| Model-assisted reading | `versum.deepen.Deepener` (default `NullDeepener`), identity resolver, concept judge: injected adapters over bounded candidates; index, capture and curation run with zero model calls |
| Curation | `suggest` · `confirm --min-sources N` · `canon`; confirmed decisions persist across re-index |
| Adapters | `adapt --adapter loomground --observation …`; `versum.loomground` builds `reasoning.interop` requests |
| Claim model | one source + exact character span per claim; predicates project onto 5D; nD systems (`validate-nd`). A normative (operator) claim's `dimension` column is empty (an *ought* carries no 5D dimension, under any name); its action type is never written to `claims.csv` at all — it lives only as a not-asserted entry in the entry model (`entries.csv`/`entry_claims.jsonl`), linked back by an `embeds` link and referenced by the deontic `action` nD coordinate. A norm with no extractable action span abstains (`ACTION_IMPLICIT`) instead of a placeholder entry. `save_claims` raises `ClaimProvenanceError` for any row lacking an asserted provenance chain (verification + source + span) — see [docs/architecture/planes.md](docs/architecture/planes.md) |
| Coordinate queries | `coords <store> <entry-id>` · `cell <store> --where sys.axis=value`; fail closed on an unknown entry/system/axis — see [docs/coordinates.md](docs/coordinates.md) |

25 subcommands: `versum --help`. Contracts: [specification](docs/reference/specification.md) · [evidence ledger](docs/reference/evidence.md) · [sink contract](docs/reference/dimensioned-subgraph-ingestion.md) · [CLI guide](docs/guides/cli.md) · [coordinate queries](docs/coordinates.md) · [nD on the index](docs/nd-on-index.md) (5D is what IS; O/P/F are OUGHT and carry no 5D dimension under any name).

## Family

Span-grounded knowledge and evidence plane; the single persistent knowledge layer; distinguishes storage, retrieval, model-assisted reading.

- consumes: [loomground-ingest](https://github.com/flxk1/loomground-ingest) envelopes · [loomground-governance](https://github.com/flxk1/loomground-governance) `>=0.8,<0.12` · [loomground-deontic](https://github.com/flxk1/loomground-deontic) `>=0.1,<0.3`
- consumed by: [loomground-solver](https://github.com/flxk1/loomground-solver) (corpus adapter, `reasoning.interop`) · agents (music-rights, digital-law)
- pipeline: `source → loomground-ingest → loomground-versum → loomground-solver → applied or diagnostic planes`
- boundary: claims and conflicts are recorded here; priority resolution and governance sit in solver and host planes

Rationale: [docs/architecture/rationale.md](docs/architecture/rationale.md).

## Status

- version 0.14.0 · specification 1-draft · alpha (formats and CLI subject to change)
- 756 tests passed, 13 skipped, 0 failing (`python -m pytest -q`, with
  `requirements-planes.txt` installed for the five-plane acceptance suite)

- python >=3.10 · 7 skills (`skills/`)

## How this is made

The code and documentation are written with Loomground agents. The maintainer reads and corrects all of it.

## License

Apache-2.0 — `LICENSES/Apache-2.0.txt`, `NOTICE`.
