---
name: loomground-kg-chat
description: Conversational, read-only Q&A over the Loomground Versum knowledge graph, grounded on every read, local-model-first. Concept multi-hop answers from the curated canon when canon.json is present at the KG root; claim/source-level otherwise - measure, never assume. Triggers - "what does this source ground", "which sources support this", "how are X and Y connected", "answer this from the KG".
---

# loomground-kg-chat

Ask the graph a question and get an answer grounded in it. This is the **conversational read
surface** over the Loomground Versum KG — the "chat with the knowledge graph" side. It sits
next to `loomground-kg` (the cockpit, which tracks the digest and routes work); this skill
answers questions and walks the graph. Both read through the same tool; neither writes.

## When to use

- "What does this source actually ground / assert?"
- "Which sources support this claim or concept?"
- "How are these two things connected in the graph? Walk me from X to Y."
- "What norms/obligations apply here, per the graph?"
- Any question that should be answered *from the KG* rather than from the model's memory.

Route status/coverage/"what to run next" to `loomground-kg` (the cockpit); route writes to the
capture door; use this skill to answer questions.

## More

- `references/reference.md` - full inputs, semantics, and guardrails.
- `references/eval.json` - what it wraps, determinism, and test status.
