# Install, CLI and verification guide

Text moved verbatim from the README (2026-09-09).

## Install

```bash
git clone https://github.com/flxk1/loomground-versum.git
cd loomground-versum
pip install -r requirements-dev.txt   # git-installs the pinned loomground kits
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
[Universal language and system adapters](../architecture/system-adapters.md).

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

See [Event history and replay](../architecture/event-log.md) for the integrity and
recovery contract.

All deterministic derived structures can instead be rebuilt together into a separate empty
root with `versum rebuild-projections --source … --target … --config …`. Confirmed curator
decisions are protected and are never treated as disposable cache data. See
[Projection authority and rebuilding](../architecture/projections.md).

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
python tools/check_hygiene.py
python -m compileall -q src/versum
```

GitHub CI runs the suite on the supported Python endpoints, performs high-signal Ruff and
MyPy checks, builds wheel and source artifacts, installs the wheel into a clean environment,
and exercises the installed CLI through `tools/smoke_installed.py`.

