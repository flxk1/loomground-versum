# loomground-knowledge-write - reference

## How it runs — delegates to capture-to-kg, never re-implements it

The only write implementation is
`loomground-editorial/skills/capture-to-kg/scripts/kg_capture.py`. Run this skill's
`scripts/delegate_capture.py` with the canonical capture arguments (`--spec`, `--outdir`,
and optional `--registry` / `--skip-duplicates`). The adapter forwards them unchanged.
Set `LOOMGROUND_CAPTURE_TO_KG_SCRIPT` when the editorial plugin is not in the sibling
development checkout. Missing writer means fail closed; there is no fallback write path.

## Inputs

- **spec** — capture-to-kg JSON source specification.
- **outdir** — staging directory for the KG inbox drop.
- **registry** — optional KG `source_registry.csv` for duplicate checking.

## What it returns

- The unmodified capture-to-kg JSON report: canonical URN, written artifacts,
  duplicate status, kind, and PDF status.

## Guardrails

- **No in-session fetch.** Never pulls a PDF over the network; binaries arrive out-of-band.
- **Provenance is single-history.** Never rewrites an existing source's URN by hand.
- **Candidate-only.** Never confirms axes or mints concepts — that is the curation step.
- **Contract-preserving.** Does not reinterpret the canonical writer's namespace/schema.
- **Sit on top, don't duplicate.** Reuses existing stubs/sidecars rather than re-minting.

## Pairing

This is an alias/delegation entry point into `loomground-editorial`'s live
`capture-to-kg` write leg. Placement decisions come from `loomground-organise`.
