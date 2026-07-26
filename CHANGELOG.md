# Changelog

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
