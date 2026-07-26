---
name: loomground-mental-model
description: The Versum mental-model engine - scan content into a grounded ConceptGraph and project it to the format that answers the question. One hub over scan, compose, and project, wrapping the versum engine; writes route through loomground-knowledge-write. Triggers - "build a mental model", "extract the concepts", "make a concept graph", "turn this into slides/a checklist/a diagram/SQL", "project this content as X".
---

# loomground-mental-model

One hub for the mental-model layer of Versum. Content goes in; a **ConceptGraph** comes
out — a cluster of span-anchored atoms composed into typed concepts (entity, process,
scenario) that stay grounded to the exact sources that support them — and that model is
then **projected** into whatever modality actually answers the user's question. This is a
single pipeline, not a dozen tools: the imported skills (Ingestion, Extractor, Scanners,
Translator, Pipeline, Persist, Register, Universal Entity, Content-to-Format, Multimodal
Explainer, and the Project-to-\* outputs) are **stages and output targets of this one hub**.

## When to use

- The user wants the structure of some content made explicit: "what are the key concepts",
  "map this", "build a mental model", "show me how this fits together".
- The user wants content re-projected: "turn this into slides / a checklist / a diagram /
  SQL / a quiz / a one-pager for my board".
- The user wants to interrogate the model: "what does this source actually support",
  "which sources back this claim".
- Building a digital twin of an entity (system, process, organisation, product) from documents.

Do NOT use it to invent concepts a source does not ground, to guess a citation, or to write
to the graph without confirmation — those are the write path's job, gated by a human.

## More

- `references/reference.md` - full inputs, semantics, and guardrails.
- `references/eval.json` - what it wraps, determinism, and test status.
