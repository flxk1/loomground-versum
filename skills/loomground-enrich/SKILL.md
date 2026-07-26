---
name: loomground-enrich
description: Grow the Versum graph from research findings - extract KG-worthy nodes, validate against the graph, propose with confidence; writes route through loomground-knowledge-write with confirmation. Triggers - "add what we learned to the graph", "enrich the KG from this", "capture these findings", "grow the graph from this conversation".
---

# loomground-enrich

The feedback loop that lets the graph learn from a working session. Where
`loomground-mental-model` builds a ConceptGraph *from a document* and
`loomground-knowledge-write` admits *a source*, this skill takes the **findings of research or
analysis** — the useful nodes produced during a conversation — validates them against what the
graph already holds, and proposes the net-new ones with a confidence score. A person confirms;
the write goes through the one door.

## When to use

- After a research or analysis session: "add what we found to the graph."
- Turning a conversation's conclusions into durable, grounded nodes.
- Periodically closing the loop so the graph reflects recent work, not just ingested files.

Do NOT use it to write directly, to add a node grounded only in model recall, or to auto-merge
without confirmation.

## More

- `references/reference.md` - full inputs, semantics, and guardrails.
- `references/eval.json` - what it wraps, determinism, and test status.
