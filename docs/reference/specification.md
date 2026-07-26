# Versum specification

**Status:** Normative
**Version:** 1-draft
**Last verified:** 2026-07-19

## Boundary

Versum extracts, indexes, relates, and selects provenance-grounded knowledge. It preserves
ambiguity and conflict. It does not decide which claim governs, resolve normative conflicts,
or construct an authoritative consistent world.

## Identity and provenance

An attached registry owns canonical source identity. Versum reuses `canonical_urn` and
version identity when supplied. In standalone mode it resolves canonical identifiers and
then content identity deterministically. A claim refers to one source and an exact cleaned
text span. Derived layers may be regenerated without changing provenance.

### Source admission

`versum capture <folder>` is the idempotent batch write path. `versum capture-file <source>
--target <folder>` is the single-source write path. A source outside the target is copied into
the target before indexing. Existing files are never overwritten; a distinct source sharing a
basename receives a content-prefixed storage name and content identity where necessary.

Single-file admission emits a JSON report with admission state, canonical identity, source and
target paths, stub and sidecar paths, claim count, fingerprint, and index manifest. Input and
extraction failures emit a stable error code and non-zero process exit. Neither path performs
network acquisition.

## Federation-5D

Federation-5D is the flat edge-reasoning algebra defined in `src/versum/dimensions.py`:

```text
structural, causal, intentional, temporal, relational
```

The string values and 25-entry composition table are an interoperability contract. A profile
maps every local predicate to one Federation dimension. The local predicate remains the finer
description and is never replaced by its projection.

Predicate, modality, polarity, and quantification are profile-local claim form. They are not
additional Federation dimensions.

## nD contextual systems

nD is an open collection of typed, namespaced, versioned coordinate systems. Versum supplies
the domain-neutral `versum-context` system. Users may register additional systems through
declarative JSON, or YAML when the optional YAML parser is installed.

Each axis declares its value type, cardinality, vocabulary mode, supported primitive
relations, optional ontology identity/version, and provenance requirement. Vocabulary modes
are `closed`, `open`, and `external`.

Primitive relations are:

```text
equal, contains, contained_by, overlaps, disjoint, precedes, succeeds
```

An axis supports only the primitives it declares. An unattested relationship returns
`unknown`. Compatibility, applicability, or conflict are derived diagnostics rather than
primitive facts and must retain their primitive explanation.

## Coordinate assignments

An nD coordinate is an assertion, not an unqualified node property:

```text
assignment_id, subject_id, system_id, system_version, axis_id, value,
source_id, method, confidence, verification
```

Values are JSON-encoded when persisted to CSV so quantities, lists, and structured values
round-trip without ambiguity. Registry and sidecar coordinates retain their source and
attestation method.

## Bindings

A binding connects profile-local claim form to contextual variables:

```text
binding_id, claim_id, form_slot, semantic_role, assignment_id,
axis_id, value, source_id, method, confidence, verification
```

Examples include `quantification.range`, `predicate.agent`, `predicate.patient`,
`modality.bearer`, and `condition.antecedent`. Each nD system declares which axes a form slot
may bind. Missing required context is reported as incomplete; it does not invalidate the
claim's provenance.

## Edge families

Versum distinguishes:

- `provenance` — source, version, claim, and span relations;
- `grounding` — claim-to-concept evidence with a semantic role;
- `binding` — claim-form slot to nD assignment;
- `scope` — primitive nD relations;
- `semantic` — candidate correspondence among concepts;
- `composition` — typed participant roles in a larger model.

Typed edges add `edge_family`, Federation `dimension`, `semantic_role`, `scope`,
`applicability`, `evidence_ids`, and `method_version` to the legacy edge columns. Legacy rows
remain readable as semantic edges. Each new typed edge requires valid endpoints, a Federation
dimension, and the role required by its family.

## Concepts and compositions

Concept identity is content-derived and never source-derived. Claims ground concepts
many-to-many. Morphological normalization may merge identity while retaining surface forms.
Unsupported or noisy concepts are deprecated or held as candidates; confirmed provenance is
not silently deleted.

A composition is not defined by co-occurrence alone. Co-occurrence may propose it, but typed
component roles provide its semantics. Existing pair composites remain compatible candidates.

## Fingerprints and retrieval

A source fingerprint has three projections:

- `federation_5d` — distribution over the five universal edge dimensions;
- `form_profile` — distribution over profile-local claim-form values;
- `context_footprint` — attested nD coordinates;
- `concept_footprint` — grounded concept identifiers.

`dim5` and `nd` remain compatibility aliases during migration. A URN identifies the source;
the Federation histogram is not its semantic address. Concept footprints support semantic
neighbourhood. Hybrid facet/BM25/dense retrieval remains a separate index.

## User-defined nD packages

A package may declare axes, vocabularies, ontology relations, form bindings, coordinate
sources, validation policy, examples, and tests. It may not redefine Federation-5D, contain
executable configuration, infer equivalence from labels, or introduce unversioned external
ontologies. Cross-system equivalence requires an explicit versioned mapping.

Validate packages with:

```bash
versum validate-nd path/to/system.json [path/to/another.json]
```

Attach them during indexing with repeatable options:

```bash
versum index <folder> --nd-system path/to/system.json
```

The index records system manifests under `.versum/nd/`, coordinate assignments in
`assignments.csv`, and form bindings in `bindings.csv`.

## Verification invariants

### External language and system adapters

An external grammar or system enters Versum only through a versioned adapter projection.
The projection MUST preserve the source-local predicate and system identity, MUST declare
the Federation-5D dimension of every semantic relation, and MUST attach provenance to every
nD coordinate assignment. A structural fallback MAY represent syntax-tree containment but
MUST NOT infer semantic dimensions or contextual coordinates from grammar productions.

Adapter mappings, source grammar, source vocabulary or policy ladders, and Federation-5D
version are identity-bearing inputs. A change to any of them MUST change the projected
system version or adapter mapping version.

- Federation values and composition remain stable.
- Every built-in profile predicate has an explicit Federation projection.
- User axes are globally namespaced and versioned.
- Closed vocabularies reject undeclared values.
- External vocabularies declare ontology id and version.
- Required coordinate provenance cannot be omitted.
- Bindings follow the declaring system's slot/axis contract.
- Primitive absence remains unknown.
- New typed edges satisfy their family contract.
- Existing files and graph rows remain readable during migration.
