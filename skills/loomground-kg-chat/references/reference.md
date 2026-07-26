# loomground-kg-chat - reference

## Ground first, always

Never state KG content from memory. Every answer runs the read tool and quotes it.

```
export LOOMGROUND_KG_CONFIG="/abs/path/to/loomground-kg.config.json"
python3 <loomground-kg skill dir>/scripts/kg_query.py <verb> …
```

The read path is the cockpit's `kg_query.py` (read-only, stdlib, no network) plus the engine's
own query verbs:

- `status` — graph shape: libraries, works, claims, reuse rate, concept count.
- `urn <canonical_urn>` — a source's 5D+nD fingerprint and sample claims (source → models).
- `search <term> [--limit N]` — sources whose claims mention a term.
- `versum models <folder> <urn>` — which models a source supports.
- `versum sources <folder> <concept_id>` — which sources ground a model.

## Local-first answer ladder

Spend the least model power that answers the question grounded.

- **No model.** A direct lookup (`status`, `urn`, `search`, `models`, `sources`) is pure
  computation — quote it and answer.
- **Local model.** When the question needs the reads composed into prose, or a term mapped to
  the right concept, a local model reads the graph output and drafts the answer. Local first —
  the corpus may be sensitive and the local path never leaves the machine.
- **Hosted model — opt-in only.** Reserve for genuinely hard multi-hop synthesis, and only if
  the user has opted in. If not, give the grounded reads and say what a stronger reader would add.

## Honest limits

- **Concept layer not curated yet** (`status` shows `concepts: 0` until `loomground-mental-model`
  runs `suggest`→`confirm`→`canon`). Until then, "which *models* / multi-hop over concepts" is
  answered at the **claim/source level** via `search`, not by true concept nodes. Say so.
- **Read-only.** No writes, no in-session fetch; no answer without shown `kg_query` output.
- **Grounded or declined.** If the graph does not support an answer, say what is missing rather
  than filling the gap from memory.

## Relationship to the other hubs

- **loomground-kg** — the cockpit (digest + routing); shares the read tool with this skill.
- **loomground-mental-model** — curates the concept layer this skill navigates; run it first to
  turn claim/source answers into true multi-hop concept answers.
- **loomground-knowledge-write** — the only write path; this skill never writes.

