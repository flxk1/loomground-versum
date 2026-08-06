# Changelog

## [0.12.0](https://github.com/flxk1/loomground-versum/compare/loomground-versum-v0.11.0...loomground-versum-v0.12.0) (2026-08-06)


### Features

* `iter_records_from_transactions` + `tombstones_from_bytes` — read the sink's records from IN-MEMORY transaction payloads instead of an on-disk store, so a consumer serving a *sealed* workspace (whose decrypted transactions live only in memory, never plaintext on disk) can read knowledge without materialising the store. Same identity-upsert latest-wins projection and record shape as `iter_records`; `tombstones_from_bytes` builds the erasure projection from the `_erasure.json` bytes. Unblocks the RVND memory-split body-drop over sealed workspaces.

## [0.11.0](https://github.com/flxk1/loomground-versum/compare/loomground-versum-v0.10.0...loomground-versum-v0.11.0) (2026-08-06)


### Features

* `append_records` — batch identity-upsert: many mutable records in ONE dimensioned-subgraph transaction (one durable fsync) instead of one per record. The batched analogue of `append_record(identity=True)` for a consumer that persists N changed rows per flush (an RVND grounder store retirement / bulk import), amortising the durable per-transaction write and leaving one transaction to validate on read. Read-side latest-wins per node id is identical; an empty batch is a no-op; idempotent by canonical `(records, versions, dimension, actor)`.

## [0.10.0](https://github.com/flxk1/loomground-versum/compare/loomground-versum-v0.9.0...loomground-versum-v0.10.0) (2026-08-06)


### Features

* `append_record(identity=True, version=…)` — opt-in identity-upsert for MUTABLE records: a stable node id `record:<slug>` (no content hash) plus a caller-supplied monotonic `version` folded into the idempotency key, so an entity edited in place supersedes its prior state instead of forking a node per edit. The read projection (`iter_records`/`get_record`/`search_records`) collapses identity records to their latest version per id; content-addressed records and facts embed a content hash, never collide, and stream unchanged (backward-compatible). Erasure by the stable id hides all revisions. Unblocks the RVND grounder-store retirement and the memory-split body-drop.

## [0.9.0](https://github.com/flxk1/loomground-versum/compare/loomground-versum-v0.7.0...loomground-versum-v0.9.0) (2026-08-06)


### Features

* `append_record` — a full runtime **record** (an RVND-style problem/solution pair with arbitrary domain facets) as first-class knowledge, the rich analogue of `append_fact`; the whole pair body rides losslessly in the node's `properties.record`, searchable through the existing read path ([e1cf3e2](https://github.com/flxk1/loomground-versum/commit/e1cf3e2))
* `iter_records` — erasure-honoring enumeration of the sink, the companion to `get_record` (by id) and `search_records` (by query) for consumers that must list or re-index everything the store holds ([5c17d69](https://github.com/flxk1/loomground-versum/commit/5c17d69))
* `BM25.score` optional `weights=` — down-weight expanded/synonym query terms; `weights=None` is exactly the historical unweighted score (backward-compatible), so a consumer can keep query-expansion weighting while consuming versum's BM25 ([f201e07](https://github.com/flxk1/loomground-versum/commit/f201e07))
* runtime knowledge-append API — `append_fact` / `append_inference` write source-less runtime knowledge (a fact triple, a reasoning path) through the canonical dimensioned-subgraph sink as an explicitly-marked runtime provenance class (`grounding="runtime"`, no manufactured grounding), idempotent and searchable through the existing read path ([7cd44cf](https://github.com/flxk1/loomground-versum/commit/7cd44cfcca72d8c57a8c2b938e85a5cf5a07f222))
* full-record retrieval over the sink — `get_record` / `search_records` return the whole node (type + dimensions + all properties), every relation touching it (both directions) and the transaction's `source` / `evidence` provenance, not a lossy snippet ([d94151f](https://github.com/flxk1/loomground-versum/commit/d94151f5909ac4b7858fa9b849d221433a335d42))
* search the dimensioned-subgraph store via `from_dimensioned_store` (one Doc per subgraph node, ranked by the shared `search_similar`) ([71164f3](https://github.com/flxk1/loomground-versum/commit/71164f31f34882aff87ea1622952a855e194a4f3))
* store search, erasure / GDPR-purge, publish + folder hierarchy over the sink store ([c417c91](https://github.com/flxk1/loomground-versum/commit/c417c91077e2860893bc29260c3b1aabfdddf121))
* honor erasure / distribution / hierarchy in the sink store ([9090d65](https://github.com/flxk1/loomground-versum/commit/9090d65ff47e36629a894e2ea8d4b037a29fd63f))
* dedupe-audit operation for duplicate-identity sources ([a74c9fb](https://github.com/flxk1/loomground-versum/commit/a74c9fbe25906a343fdebf6d9e36cc66a5a279ac))


### Bug Fixes

* serialize store writers with an exclusive journal lock ([ca03bfb](https://github.com/flxk1/loomground-versum/commit/ca03bfbdffbd3f4b779afa173f08e97255e2862b))
* treat the CELEX `_SUM` qualifier as document identity ([0c8484d](https://github.com/flxk1/loomground-versum/commit/0c8484d3cbf09c25a60fee89d10a8e601bf50828))
* treat the CELEX `_INF` qualifier as document identity too ([5b1f823](https://github.com/flxk1/loomground-versum/commit/5b1f8235e96076368549ae2f5ee44cdc15d14ed4))


### Build System

* gate the PyPI publish behind the `PYPI_PUBLISHING` repo variable ([0ba5325](https://github.com/flxk1/loomground-versum/commit/0ba5325048e7da7fdd947c955a7515723d8148e6))

## [0.7.0](https://github.com/flxk1/loomground-versum/compare/loomground-versum-v0.6.4...loomground-versum-v0.7.0) (2026-08-02)


### Features

* first-class stub-bytes pairing operation ([e5e4be9](https://github.com/flxk1/loomground-versum/commit/e5e4be9d5ac5eb23f6a6dff1ed2365017e24589b))
* markdown overlay projection written back into the library ([1fdd94e](https://github.com/flxk1/loomground-versum/commit/1fdd94e493346c9a080d54f565e0d181c7a2034a))
* regenerate the overlay projection as part of sync ([d2e2e14](https://github.com/flxk1/loomground-versum/commit/d2e2e144457d5743c984b23b4af2283b77b395f5))


### Bug Fixes

* exclude hidden paths from the Live Index walk ([6a66b0a](https://github.com/flxk1/loomground-versum/commit/6a66b0ab7277ff83e2275db770750bba8a622838))
* exempt workspace housekeeping files from inbox orphan audit ([7021b18](https://github.com/flxk1/loomground-versum/commit/7021b1820a263b1b3efef0bccc1ddd56b2a7b71b))
* honour KG metadata sidecars in Live Index sync ([612a78e](https://github.com/flxk1/loomground-versum/commit/612a78eafb968f3fa610cde82484a64d16115db8))
* keep overlay note names within the filename byte limit ([12beeb7](https://github.com/flxk1/loomground-versum/commit/12beeb70309655e815c896f2c9260a3005cbeb27))
* keep release manifests coherent ([#7](https://github.com/flxk1/loomground-versum/issues/7)) ([ca225f6](https://github.com/flxk1/loomground-versum/commit/ca225f6fa860246b127b2695eaeb2e8a12573ede))
* percent-encode overlay link destinations ([440ff06](https://github.com/flxk1/loomground-versum/commit/440ff064d24de862eb6e3df2d188d15ab69cc65f))
* tolerate Finder cruft in the K1 legacy-baseline walk ([8603fff](https://github.com/flxk1/loomground-versum/commit/8603fffb2184f6e36376afd9270f3772376d197f))
* tolerate impossible sidecar filenames ([#6](https://github.com/flxk1/loomground-versum/issues/6)) ([9ca3786](https://github.com/flxk1/loomground-versum/commit/9ca3786fa35b70225c0c655fd9b65993ccdd9822))


### Documentation

* document loomground-deontic runtime dependency ([7dc6346](https://github.com/flxk1/loomground-versum/commit/7dc6346087e44f0d027e05714300658d6ac81654))
* document loomground-deontic runtime dependency ([187b1a7](https://github.com/flxk1/loomground-versum/commit/187b1a7bacd014b353c2de3540f36fc46b7725ef))
* neutralise retired corpus-name remnants ([5602729](https://github.com/flxk1/loomground-versum/commit/56027295480863b8f2ab65f7dc1c3d8733e8517b))

## [0.6.4] - 2026-07-26

- Pin the privacy-clean Governance and Deontic publication roots.

All notable release changes are documented here. Versions follow Semantic Versioning while
the project is in alpha; minor releases may intentionally change the public CLI or file format.

## [Unreleased]

## [0.6.3] - 2026-07-25

### Added

- A public dimensioned-subgraph sink with contained atomic persistence,
  idempotency, versioned receipts, and a supported read surface for Solver
  adapters.

### Changed

- Include persisted dimensioned subgraphs in snapshot identity and document
  the canonical Ingest-to-Versum ownership boundary.

## [0.6.2] - 2026-07-25

### Changed

- Depend on `loomground-governance` (the renamed upstream language distribution)
  instead of `loomground-language`, resolved from its `v0.8.0` release.

## [0.6.1] - 2026-07-24

### Changed

- `docs/planning/` removed. Its coherence plan and concept-audit findings documented a
  plan whose every workstream is now implemented or superseded, and whose
  conceptual-model summary duplicated, in less detail, what
  `docs/reference/specification.md` already covers; nothing in it was uniquely
  load-bearing. History remains in Git.
- The graph viewer's HTML moved out of `viewer_template.py` (previously a Python
  r-string) into a real `src/versum/viewer.html`, packaged via
  `[tool.setuptools.package-data]` and loaded through `importlib.resources`. No
  behavior change; `export --format html` produces byte-identical output.

### Fixed

- Three test fixtures (`test_consume.py`, `test_extract_law.py`,
  `test_fingerprint_nd.py`) no longer hardcode a personal machine's file paths; they
  read `VERSUM_REGISTRY_CSV`, `VERSUM_INBOX_DIR`, and `VERSUM_CELEX_PDF` from the
  environment instead, with an actionable skip reason when unset.
- The author name is now `Loomground Contributors` consistently across `package.json`,
  `.claude-plugin/plugin.json`, `NOTICE`, `REUSE.toml`, and the README.

## [0.6.0] - 2026-07-24

### Changed

- Reorganized `src/versum`'s ~40 flat top-level modules into four subpackages by role:
  `identity/` (source identity, URNs, fingerprints, evidence), `concept/` (the mental-model
  curation layer), `store/` (the graph model and how callers read/write it), and `io/`
  (claim extraction and registry consumption). Modules that are themselves CLI entry
  points (`sync`, `write`, `run`, and others) stay at the top level. This is a breaking
  change for anyone importing `versum` submodules directly (`from versum.graph import
  ...` is now `from versum.store.graph import ...`); the `versum` CLI's public interface
  is unaffected.

### Added

- `config.example.json` (the `sync`/`seed-state`/`watch --config` file format) is now
  packaged in the built wheel; previously it existed only in the source checkout.
- A coherence check (`tests/test_manifest_coherence.py`) keeps `pyproject.toml`,
  `package.json`, and `.claude-plugin/plugin.json` agreeing on name and version, so they
  can no longer drift apart silently.

### Fixed

- Tests that transitively require the Loomground kit (any test that indexes or syncs a
  corpus) now skip with an actionable reason instead of failing with a raw
  `LoomgroundSourceError` when the kit isn't installed.

## [0.5.2] - 2026-07-24

### Added

- Replayable event log and rebuildable projections: an empty graph root can be reconstructed
  from its event history, with a watermark-based change feed for downstream consumers.
- A store-backed evidence facade with bounded batch verification, and a required
  `graph_version` stamp on every sync and write record.
- A universal system adapter framework that projects canonical system observations, including
  Loomground's, into typed graph coordinates.
- Persisted native claim semantics alongside the existing Federation-5D projection.
- Graph export (`versum_graph/v1` payload and GraphML) and an offline HTML viewer with
  floating per-node source cards.
- A concept-layer curation skill: cross-source recurring-term mining, a closed-class
  function-word filter, transliterating slugs, and umlaut-aware German stemming.
- PDF extraction now skips ruled-table regions instead of misreading them as prose.
- The Claude plugin (knowledge write, organise, mental-model, enrich, KG query, KG chat,
  curate) shipped in-tree alongside the engine.

### Fixed

- The `loomground-governance` dependency now resolves from a tagged release instead of an
  unpinned Git branch, so installs are reproducible and no longer depend on a submodule that
  pointed at the wrong repository.

### Known limitations

- Concept normalization, automatic canon convergence, and model deepening remain experimental.
- Custom nD extraction adapters, broader composition grammars, and external corpus quality gates
  are not bundled.

## [0.1.0] - 2026-07-20

### Added

- Provenance-grounded folder indexing and guarded single-file or batch capture.
- Typed claims, Federation-5D projection, extensible nD systems, and coordinate bindings.
- Deterministic concept suggestion, confirmation, grounding traversal, and hybrid retrieval.
- Incremental synchronization and optional model adapters constrained by deterministic policy.
- Standalone packaging with no dependency on retired product repositories or legacy writers.

[Unreleased]: https://github.com/flxk1/loomground-versum/compare/v0.6.4...HEAD
[0.6.4]: https://github.com/flxk1/loomground-versum/compare/v0.6.3...v0.6.4
[0.6.3]: https://github.com/flxk1/loomground-versum/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/flxk1/loomground-versum/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/flxk1/loomground-versum/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/flxk1/loomground-versum/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/flxk1/loomground-versum/compare/538a221...4d1ac68
[0.1.0]: https://github.com/flxk1/loomground-versum/commit/538a221
