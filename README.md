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
| Claim model | one source + exact character span per claim; predicates project onto Federation-5D; nD systems (`validate-nd`) |

23 subcommands: `versum --help`. Contracts: [specification](docs/reference/specification.md) · [evidence ledger](docs/reference/evidence.md) · [sink contract](docs/reference/dimensioned-subgraph-ingestion.md) · [CLI guide](docs/guides/cli.md).

## Family

Span-grounded knowledge and evidence plane; the single persistent knowledge layer; distinguishes storage, retrieval, model-assisted reading.

- consumes: [loomground-ingest](https://github.com/flxk1/loomground-ingest) envelopes · [loomground-governance](https://github.com/flxk1/loomground-governance) `>=0.8,<0.12` · [loomground-deontic](https://github.com/flxk1/loomground-deontic) `>=0.1,<0.2`
- consumed by: [loomground-solver](https://github.com/flxk1/loomground-solver) (corpus adapter, `reasoning.interop`) · agents (music-rights, digital-law)
- pipeline: `source → loomground-ingest → loomground-versum → loomground-solver → applied or diagnostic planes`
- boundary: claims and conflicts are recorded here; priority resolution and governance sit in solver and host planes

Rationale: [docs/architecture/rationale.md](docs/architecture/rationale.md).

## Status

- version 0.13.0 · specification 1-draft · alpha (formats and CLI subject to change)
- 542 tests passed, 15 skipped (`python -m pytest -q`)
- python >=3.10 · 7 skills (`skills/`)

## License

Apache-2.0 — `LICENSES/Apache-2.0.txt`, `NOTICE`.
