# Versum evidence ledger

**Status:** Current evidence
**Last verified:** 2026-09-28

## Automated verification

With `requirements-dev.txt` and `requirements-planes.txt` installed, as CI does, the full
local suite passes:

```text
756 passed, 13 skipped
```

The skipped tests need external corpus fixtures, the sibling language or solver
repositories, the optional loomground-editorial integration, or `reportlab`. The Loomground
grammar tests consume the
pinned `loomground-governance` release; no network is used by the core test suite. Repository hygiene,
bytecode compilation, and CI's high-signal Ruff selection also pass locally, as do the isolated
distribution build and the installed-wheel smoke.

New coherence-contract coverage verifies:

- the five 5D enum values and complete 25-entry composition algebra;
- total 5D predicate projections for all four built-in profiles;
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

These findings motivate the separate form profile, context footprint, concept
footprint, and retrieval index in the normative specification.

## Current limitations

- Versum has no runtime or release dependency on retired product repositories or their
  legacy write paths. Its Git-sourced package dependencies are the neutral
  `loomground-governance` and `loomground-deontic` adoption kits, each pinned to a
  tagged release of its canonical repository.

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
  responsibilities of conforming tools rather than Versum. Versum likewise consumes the
  data-only `loomground-deontic` pack to build the deontic (governance-facet) nD system,
  adding no vocabulary of its own.
- Whole-registry, citation-majority, multi-profile gold-set, performance, and corpus-quality
  gates still require external fixtures and are not represented as completed local evidence.
