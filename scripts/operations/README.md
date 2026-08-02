# Bulk corpus operations

One-shot scripts for building or rebuilding a KG store from a large corpus, config-driven
via the same `config.example.json` format the `sync`/`seed-state`/`watch` CLI commands use
(see `--config` in each script and the top-level README's "Using it" section). None of
these run in CI or ship as part of the installed package; they operate directly on a real
`kg_root` the caller points them at.

- `migrate_full.py` — the initial bulk build: indexes every domain of every configured
  library in parallel, resumable, read-only on the corpus.
- `reextract_full.py` — re-extracts an existing KG's claims (for example after an
  extractor fix) and resets each domain's curation output (`concepts.csv` /
  `semantic_edges.csv`) to empty, since the claims underneath changed.
- `curate_full.py` — rebuilds the concept-layer canon on top of the (re)extracted claims.
- `remediate_stub_provenance.py` — repairs a store that minted parallel URNs for KG
  citation stubs / sidecar-carried sources (before the Live Index honoured
  `*.metadata.json` sidecars). Read-only audit by default; `--apply` runs the sanctioned
  re-index cascade (`sync_once(..., force_reextract=True)`) — never hand-edits store CSVs.

Run order when re-extracting: `reextract_full.py` first, then `curate_full.py` — curation
reads the claims `reextract_full.py` just regenerated.
