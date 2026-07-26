# loomground-kg - reference

## How it runs — reads the graph via kg_query.py, never writes

The work is `scripts/kg_query.py`, a read-only Python script (stdlib, no network) that
queries the Versum knowledge graph. The script reads `LOOMGROUND_KG_CONFIG` for device
paths; the skill holds no machine paths and runs unchanged on any machine with a config.

Commands:
- `status` — libraries, domains, distinct works, claims, reuse rate, concept count.
- `urn <canonical_urn>` — a source's 5D+nD fingerprint + sample claims.
- `search <term> [--limit N]` — sources whose claims mention a term.
- `libraries` — the configured libraries and their roots.

## Inputs

- **LOOMGROUND_KG_CONFIG** — environment variable pointing to the config file.
- **command** — one of `status`, `urn`, `search`, `libraries`.
- **arguments** — command-specific (URN for `urn`, term for `search`).

## What it returns

Structured KG state: library counts, domain coverage, source fingerprints, claim samples,
concept counts. Never invents state — every response is grounded on actual `kg_query.py`
output.

## Guardrails

- **Read-only.** Never writes to the graph; writes route through `loomground-knowledge-write`.
- **Ground first.** Always run the read tool before stating KG state — never from memory.
- **No in-session fetch.** Never pulls documents over the network.
- **Config-driven.** All device paths live in the config file, not in the skill.

## Pairing

Routes work to `loomground-editorial`, `capture-to-kg`, `loomground-course-orchestrator`.
Questions about graph writes hand off to `loomground-knowledge-write`.
