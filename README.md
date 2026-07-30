# Versum

> The normative contracts are in the [specification](docs/reference/specification.md);
> current verification and limitations are in the [evidence ledger](docs/reference/evidence.md).

Versum turns a folder of documents into a knowledge graph. You point it at a
directory, and it reads each file into span-anchored, typed atoms, then composes those
atoms into the recurring mental models the collection is really about. It is a general
engine: nothing about it is tied to a subject area. The examples in this document happen
to use European data-protection law because that was the first corpus to hand, but the
engine privileges no domain — the vocabulary for any field is supplied by a swappable
profile, and the concepts a corpus contains are discovered from the corpus itself.

The design goal is a graph you can trust. Every claim the engine records is anchored to
an exact span of an exact source, drawn from a closed vocabulary, and checked by
invariants — so the base layer cannot fabricate. Language models are used, when they are
used at all, on rails: they read and compose within the constraints the deterministic
layer sets, and their output is verified before it is stored. Most work needs no model.

## Capability status

- **Operational:** provenance reuse, deterministic identity, span claims, Federation-5D
  projection, profile-local claim form, typed nD systems and assignments, concepts,
  many-to-many grounding, universal system adapters, Loomground semantic projection,
  hybrid retrieval, and incremental sync.
- **Experimental:** concept normalization, automatic canon convergence, typed pair
  compositions, and optional model deepening.
- **Designed:** richer process/conditional/relation/diff composition grammars and broader
  custom nD extraction adapters.
- **Outside Versum:** governance, priority resolution, and authoritative world construction.

## What it builds

The graph begins with a **provenance spine** of canonical sources and versions. The **claim
layer** binds each typed assertion to one source and exact character offsets. Claims retain
their profile-local form and project their predicate onto the flat Federation-5D edge algebra.
Their typed nD assignments record contextual scope. Provenance and claims never silently
move or merge.

The **concept layer** sits on top. A mental model is not a single atom but a
*composition* of them — a cluster of atoms about one term becomes an entity concept, a
sequence ordered in time becomes a process, a set of conditions becomes a scenario. The
engine proposes these compositions with deterministic grammars and records them as a
separate, regenerable layer linked back to the atoms that ground them. A concept can be
grounded by many documents, and a document can feed many concepts; that many-to-many
grounding is what lets you ask, in both directions, which models a source supports and
which sources support a model.

Concepts are expected to *converge*. Within a domain there is a bounded canon of mental
models, so as documents accumulate each new one mostly re-uses concepts already seen and
adds only a little. A healthy run shows that new-concept rate decaying toward zero; a run
that never settles is producing noise, not knowledge. Convergence, not raw count, is the
signal that the graph is good.

## Design principles

The engine follows a few commitments that are worth stating plainly, because they shape
every part of it.

*Deterministic floor, model on the rails.* Identity, deduplication, span extraction,
axis validation, and the invariants are plain Python and run with no model. Where reading
genuinely needs judgement — a messy citation, a concept that must be merged across
phrasings or languages — a model is invited in, but only to choose from the closed
vocabularies and grounded in a given span, and its output is verified before it counts.
The model never runs on the happy path and never has the last word without a check.

*Local-first and model-agnostic.* The engine ships no model and names no provider. It
exposes a small interface — a resolver for ambiguous identity, a judge for concept
hygiene — and any backend clicks into it: a local model, an OpenAI-compatible server, a
hosted API, or nothing. See the [model boundary](docs/architecture/model-boundary.md) for the
exact boundary. The optional `versum.integrations.ollama` adapters are the one exception to
"no network": wiring one in makes real HTTP calls to a local Ollama server. No shipped skill
does this by default; it is available only if you instantiate it yourself. The engine's own
no-network test (`tests/test_no_network.py`) deliberately excludes `integrations/` for this
reason.

*Domain is neutral and per-document.* A folder is just a bag of files and may hold many
subject areas at once; a single document may touch more than one. Domain is therefore a
property of the document, not the folder, and the engine hard-codes no list of domains.
Vocabularies live in profiles (`generic` by default; add your own), gold sets and corpora
are external user data, and any domain label a concept carries is applied by a universal
rule, never baked into the core. A test guards the core against domain leakage.

*Flat Federation-5D, extensible nD.* Every local predicate projects onto one of five stable
edge-reasoning dimensions: structural, causal, intentional, temporal, or relational. Local
predicates retain their finer meaning. Context lives in typed, namespaced and versioned nD
systems; users can add a narrow mathematical, scientific, or other contextual system through
declarative configuration without changing the engine.

## Install

```bash
git clone https://github.com/flxk1/loomground-versum.git
cd loomground-versum
pip install .
```

This installs the `versum` command. Runtime dependencies are `pdfplumber` and the
`loomground-governance` and `loomground-deontic` adoption kits, each pinned to a tagged
release of its canonical repository; installing from source therefore also requires Git. Versum supports Python 3.10 or newer on
any operating system. For development against an unreleased Loomground checkout, set
`LOOMGROUND_SOURCE` to that checkout's path instead of installing the pinned kit. Versum uses
Loomground's published data-only adoption kit and runtime-neutral protocol; it does not
reimplement the language.

## Using it

The everyday command reads a folder and writes the graph into it, under a `.versum/`
directory that persists across runs:

```bash
versum index <folder> --profile generic
```

To validate and attach user-defined nD systems:

```bash
versum validate-nd my-nd-system.json
versum index <folder> --profile generic --nd-system my-nd-system.json
```

External grammars and systems enter through the universal adapter boundary. For example,
a canonical observation from any conforming Loomground runtime can be projected into a
typed Graph-Versum layer:

```bash
versum adapt --adapter loomground --observation observation.json \
  --out .versum/adapters/loomground
```

The projection preserves Loomground's local predicates while mapping relations explicitly
onto Federation-5D and materializing its policy context as versioned nD coordinates. See
[Universal language and system adapters](docs/architecture/system-adapters.md).

`sync`, `seed-state`, `search`, `canon`, and `watch --config` share one Live Index config
file describing a `kg_root` and one or more libraries to poll. Copy the annotated template
installed alongside the package — `python -c "import versum, pathlib as p;
print(p.Path(versum.__file__).parent / 'config.example.json')"` prints its path — to a real
config, then run `versum seed-state --config <that file>` once and `versum sync --config
<that file>` incrementally.

Config-driven `sync` records every KG mutation in `<kg_root>/_events.jsonl`. Materialized
domain files, sync state, nD manifest, and graph-version stamp can be rebuilt from that
append-only history:

```bash
versum replay-events --source /path/to/kg --target /path/to/empty-replica
```

See [Event history and replay](docs/architecture/event-log.md) for the integrity and
recovery contract.

All deterministic derived structures can instead be rebuilt together into a separate empty
root with `versum rebuild-projections --source … --target … --config …`. Confirmed curator
decisions are protected and are never treated as disposable cache data. See
[Projection authority and rebuilding](docs/architecture/projections.md).

Incremental consumers can request `versum changes --kg-root … --since <watermark>` and
receive exactly the canonical URNs and claim IDs affected after that event sequence.

To add sources through the guarded write path — which resolves a canonical identifier,
refuses duplicates, and then indexes — use `capture`; it is idempotent, so re-running it
after a document lands admits only the new one:

```bash
versum capture <folder> --profile generic
versum capture <folder> --consume-registry /path/to/source_registry.csv \
  --library dls-knowledge --namespace dls
versum capture-file ./document.pdf --target <folder> --profile generic
versum watch   <folder>          # re-capture automatically whenever the folder changes
```

For a library-backed capture, `--consume-registry` reads the existing KG source registry
and reuses matching canonical URNs. `--library` records the owning library ID, while
`--namespace` controls URNs minted only for sources that have no registry match.

`capture-file` accepts one local file, copies an external file into the target without
overwriting a basename collision, and returns a stable JSON report containing its identity,
admission state, target artifact, stub and sidecar, claim count, fingerprint, and index
manifest. Missing, unsupported, empty, unreadable, malformed, and invalid-profile inputs
return machine-readable errors and non-zero exit codes. Versum never fetches a URL.

Once a folder is indexed, the curation loop proposes concepts and their grounding, and a
confirm step promotes the ones you keep:

```bash
versum suggest <folder>                 # propose concepts + grounding edges
versum confirm <folder> --min-sources 2 # promote (here: only concepts grounded in >1 source)
```

And you can walk the grounding in either direction:

```bash
versum models  <folder> <source-urn>   # which concepts a source grounds
versum sources <folder> <concept-id>   # which sources ground a concept
```

Everything a run produces — atoms, sources, fingerprints, the concept registry, the
grounding edges — lives in `<folder>/.versum/` and survives re-runs; curation output is
never overwritten by a re-index.

## Measuring quality

Quality is measured, not asserted, and it is measured against *your* data. Bring a gold
set for the domain you care about — a plain text file of one concept slug per line — and
point the optional regression at it:

```bash
VERSUM_CORPUS=/path/to/corpus VERSUM_GOLD=/path/to/gold.txt VERSUM_PROFILE=generic \
  python -m pytest tests/test_corpus_regression.py
```

The engine holds no gold set of its own. `versum/eval.py` provides the domain-general
scorer (set-based precision, recall, f1) and the convergence curve; the corpus and its
gold are yours.

## Development verification

```bash
python -m pytest -q
python scripts/check_hygiene.py
python -m compileall -q src/versum
```

GitHub CI runs the suite on the supported Python endpoints, performs high-signal Ruff and
MyPy checks, builds wheel and source artifacts, installs the wheel into a clean environment,
and exercises the installed CLI through `scripts/smoke_installed.py`.

## Layout

The `src/versum/` package is the domain-neutral engine. Profiles live in `src/versum/profiles/`;
`generic` is the neutral default. The normative contracts are in the
[specification](docs/reference/specification.md), current verification and limitations are in
the [evidence ledger](docs/reference/evidence.md), and the architectural rationale begins with
[ADR-001](docs/decisions/001-domain-general.md).

## Status

Versum is alpha software: its file formats and command-line interface may still change.
The provenance layer, folder indexer, guarded write path, and deterministic curation loop are
built and tested. The model-on-rails reader, shared per-domain canon, and scenario layer remain
open work, tracked against the normative contracts in the
[specification](docs/reference/specification.md). See the [evidence ledger](docs/reference/evidence.md)
for verified coverage and explicit limitations. Run the suite with `python -m pytest tests/`.

## Authorship

This work is authored by **Loomground Contributors** and was assisted by Claude and Codex. Claude
and Codex are acknowledged as tools, not authors or co-authors.
