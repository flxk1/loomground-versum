# loomground-enrich - reference

## The rule this skill exists to enforce

Enrichment is a **proposal a human confirms**, never an automatic write, and never an
*ungrounded* one. A candidate node earns a place only if it is (a) grounded — traceable to a
source or an explicit finding, not model recall — and (b) not already in the graph. Everything
else stays in a review list. The graph grows from evidence, not from confident prose.

## How it runs

1. **Extract candidates.** From the session's research output, pull KG-worthy nodes (concepts,
   claims, relations) with the span or finding that grounds each. Discard anything grounded only
   in the model's memory.
2. **Validate against the graph.** For each candidate, check the existing graph
   (`kg_query.py search` / `versum models` / `versum sources`): is it already present, a
   near-duplicate to merge, or genuinely new? Attach a confidence score from the strength of its
   grounding and the closeness of its match.
3. **Rank and show.** Present net-new, high-confidence candidates first; flag near-duplicates for
   merge; keep low-confidence or ungrounded ones in review. Show the grounding for each — the
   evidence *is* the reason.
4. **Confirm, then write through the one door.** On a person's confirmation, hand the accepted
   nodes to `loomground-knowledge-write` (identity, dedup, sidecar, index). This skill never
   writes to the graph itself.
5. **Report.** Return counts (new / merged / held), the confidence distribution, and the review
   list. Note that concept links remain candidate until curation.

## Local-first, model on the rails

Extraction and matching prefer the deterministic reads and a local model; a hosted model is
opt-in only, per the user's effort policy (the same dial as `loomground-organise`). The model
proposes; the graph and the person dispose.

## Guardrails

- **Grounded or held.** No node enters without a source or explicit finding behind it.
- **Single-door writes.** Every accepted enrichment goes through `loomground-knowledge-write`.
- **Confidence is shown, not hidden.** Low-confidence candidates are surfaced for review, never
  quietly written.
- **No in-session fetch.** Enrich from what the session produced; do not pull binaries over the
  network mid-session.

## Relationship to the other Versum hubs

- **loomground-mental-model** — builds models from content; this skill grows the graph from
  research output. They meet at the concept layer.
- **loomground-knowledge-write** — the one write path; this skill proposes, it calls.
- **loomground-kg / loomground-kg-chat** — read the graph this skill helps grow.

