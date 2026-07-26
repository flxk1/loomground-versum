# Versum evidence ledger

**Status:** Current evidence
**Last verified:** 2026-07-24

## Automated verification

The full local suite passes:

```text
339 passed, 10 skipped
```

The skipped tests require external corpus fixtures. The Loomground grammar tests consume the
pinned `loomground-governance` release; no network is used by the core test suite. Repository hygiene,
bytecode compilation, and CI's high-signal Ruff selection also pass locally. The distribution
build succeeds locally with build isolation disabled; the clean isolated build and installed-
wheel smoke remain CI release gates because they require dependency resolution.

New coherence-contract coverage verifies:

- the five Federation enum values and complete 25-entry composition algebra;
- total Federation predicate projections for all four built-in profiles;
- preservation of local predicates beside universal dimensions;
- loading, validation, namespacing, and coexistence of user nD systems;
- consumption and fingerprinting of the authoritative Loomground grammar in nD manifests;
- closed-vocabulary, type, quantity, and provenance validation;
- three-valued primitive ontology comparisons;
- typed coordinate-assignment and binding persistence;
- binding slot/axis contracts;
- grounding, binding, scope, and composition edge contracts;
- compatibility of legacy semantic edges;
- registration of custom nD systems in a folder index;
- collision-safe local filenames through acquire, provenance, year, and review routing.
- single-file admission for internal and external files, including duplicate, basename
  collision, empty, unsupported, malformed, missing, and invalid-profile cases;
- preservation of the synthetic PDF line-break regression and control fixtures;
- repository hygiene and bytecode compilation checks.

## Packaging and release verification

Package discovery includes the complete `versum*` namespace. GitHub CI is configured to:

- run tests at the supported Python endpoints;
- run high-signal Ruff checks and MyPy on the external boundaries;
- build wheel and source distributions;
- install the wheel in a clean environment;
- exercise CLI help, single-file capture, indexing output, and generated state without the
  repository on `PYTHONPATH`.

The exact local artifact verification command and result are recorded at release time; CI
configuration alone is not treated as evidence of a published release.

## Empirical concept-layer evidence

A 2026-07-18 corpus audit found:

- the legacy claim-form histogram is nearly domain-blind and is not a placement signal;
- concept overlap supplies the useful semantic neighbourhood;
- concept suggestion is suitable for ranked suggestion, not automatic shelving;
- morphological duplication and the hapax tail remain major quality work.

These findings motivate the separate Federation form profile, context footprint, concept
footprint, and retrieval index in the normative specification.

## Provenance integration evidence

[`provenance-proof.md`](provenance-proof.md) demonstrates canonical-URN reuse through index, suggestion, confirmation, and
both-way traversal for one real source. Its stated limitations remain: it is not a whole-
registry proof, and the citation-only majority needs separate coverage.

## Current limitations

- Versum has no runtime or release dependency on retired product repositories or their
  legacy write paths. Its only Git-sourced package dependency is the neutral
  `loomground-governance` adoption kit, pinned to a tagged release of
  the canonical `loomground-governance` repository.

- User nD packages define and validate contextual systems; specialized extraction adapters
  are not bundled.
- Core indexing materializes registry/sidecar jurisdiction and time assignments. Other custom
  assignments are supplied through the typed assignment API or future extraction adapters.
- Primitive ontology relations are direct attested facts plus directional inverses; transitive
  closure is not silently assumed.
- Typed composition roles are supported by the edge contract, while the current automatic
  composition proposer remains pair/co-occurrence based.
- Legacy purpose, canon, and inference columns remain for compatibility pending a lossless
  migration into contextual assignments and derivation records.
- Versum consumes Loomground's published `loomground-governance` adoption kit from the pinned
  GitHub repository. The kit is data-only and runtime-neutral; parsing and evaluation remain
  responsibilities of conforming tools rather than Versum.
- Whole-registry, citation-majority, multi-profile gold-set, performance, and corpus-quality
  gates still require external fixtures and are not represented as completed local evidence.
