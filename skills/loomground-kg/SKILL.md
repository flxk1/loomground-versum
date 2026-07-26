---
name: loomground-kg
description: >-
  The cockpit over the Loomground Versum knowledge graph. Use whenever the user wants to see the
  state of the KG, ask what a source grounds or what grounds a claim, check whether this week's
  digest/signals are captured in the graph, decide what to run next across the Loomground skill
  platforms, or route grounded work. Triggers include "KG status", "what's in the knowledge
  graph", "is this week's digest grounded", "what should I run next", "which sources cover X",
  "cockpit", "route this to the right skill", "what does this source ground", and "coverage of
  this domain".
---

# Loomground KG — cockpit

One control surface over the Loomground Versum KG. Two jobs: **know the digest**, and be
the **cockpit for the skill platforms**. Everything is grounded on the graph through one
read tool; nothing is invented.

## Ground first, always
Before answering anything, run the read tool and quote it — never state KG state from memory.

```
# one-time per machine: point at your KG config (all device paths live only there)
export LOOMGROUND_KG_CONFIG="/abs/path/to/loomground-kg.config.json"
python3 <this skill dir>/scripts/kg_query.py status
```
The code carries no machine paths; the single config file (see `config.example.json`) holds
`kg_root` and each library's `root_path`, so the same skill runs unchanged on any machine.
`kg_query.py` (read-only, stdlib, no network) is the single read path:
- `status` — libraries, domains, distinct works, claims, reuse rate, concept count.
- `urn <canonical_urn>` — a source's 5D+nD fingerprint + sample claims (source → models).
- `search <term> [--limit N]` — sources whose claims mention a term (claim-text lookup;
  for concept→sources, use the curated canon tables — see Honest limits).
- `libraries` — the configured libraries and their roots.

Read path = `scripts/kg_query.py`. Writes must route through the installed package that provides
the `knowledge.capture` capability — never write claims directly or fetch a PDF in-session. The
capture provider registers provenance out-of-band; the live indexer then picks it up.

## Job 1 — know the digest
The editorial weekly digest lives in the successor KG folder: `00_Inbox` (candidates),
`03_Signals/<chain>/<type>` (promoted signals), `06_Graph/timelines` + `06_Graph/connections`
(markdown, keyed by event + news URL). To "know the digest":
1. Inventory this week's signals (read `03_Signals` / `06_Graph`).
2. For each signal, check grounding: is its cited document in the KG? Use `search` on the
   signal's key terms or `urn` if you have the `canonical_urn`. Report **grounded vs pending**.
3. Route each pending signal: a signal citing a real document → `capture-to-kg`; a pure
   news event → the news/event claim model; already grounded → show the link, do nothing.
4. Report digest **coverage** (grounded / total) from the actual reads.

## Job 2 — cockpit for the skill platforms
Drive the ecosystem from one place, each answer grounded on the graph:
- **Status board.** For `loomground-editorial`, `ai-governance-watch`,
  `loomground-course-orchestrator`, `capture-to-kg`: what each last produced, what it reads
  from the KG, and what is stale (its inputs changed since it last ran).
- **Route work.** "Turn the digest into a newsletter" → `loomground-editorial` render;
  "build a lesson from concept/source X" → `loomground-course-orchestrator`; "add these
  sources" → `capture-to-kg`. Pick the platform; don't make the user pick.
- **What to run next.** Derive it from graph state: ungrounded digest signals → capture; a
  concept newly grounded by ≥N independent sources → a lesson is worth building; a domain
  with rising claim count but no recent newsletter → a draft is due.

## Commands (what to do when the user says…)
- **"kg status" / "what's in the graph"** → run `status`; summarize libraries, works, claims,
  reuse, concepts; name the biggest domains.
- **"kg digest" / "is the digest grounded"** → Job 1: inventory signals, check grounding,
  report coverage + routed next-actions.
- **"kg query <canonical_urn>"** → run `urn`; report the source's 5D+nD + what it asserts.
- **"which sources cover <term>"** → run `search`; list sources + counts.
- **"what next" / "kg next"** → Job 2 "what to run next", ranked, each with the platform to run.
- **"route: <intent>"** → pick the platform and invoke it, grounded on the graph.

## Honest limits (state them; don't paper over)
- **Measure the concept layer; never assume its state.** Read `canon.json` at the KG root:
  `n_concepts > 0` means the coordinate-identity curation has run and "which *models* does
  this source ground / which sources ground this *model*" answers at concept level — join
  `semantic_edges.csv` (`edge_type == "grounds"`) to `claims.csv` on `item_id` in the
  by-domain folders. (`versum sources`/`models` read `.versum/` watched-folder state and
  return `[]` on materialized folders — don't use them for this.) If `canon.json` is absent
  or reports 0, answer at claim/source level via `search` and recommend `loomground-curate`.
- **Digest grounding is claim/source-level** until the news/event claim model links a signal's
  news URL to a KG source. Report what is checkable now; don't assert a grounding you can't show.
- **Read-mostly.** The cockpit reads the graph and routes; the only writes go through the
  single door. No in-session fetch; reversible; no done-claim without shown `kg_query` output.
