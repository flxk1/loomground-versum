---
name: loomground-mental-model
description: The Versum mental-model engine - scan content into a grounded ConceptGraph and project it to the format that answers the question. One hub over scan, compose, and project, wrapping the versum engine; writes route through loomground-knowledge-write. Use when the user wants concepts extracted from content into a concept graph, or that content projected into another format. Triggers - "build a mental model", "extract the concepts", "make a concept graph", "turn this into slides/a checklist/a diagram/SQL", "project this content as X".
allowed-tools: versum_index versum_claims versum_search
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

## Primary path

`versum_index` with `{"folder": "<content folder>", "profile": "<profile>"}` scans a
folder of content into span-anchored claims, concepts and nD (writes `<folder>/.versum`);
`versum_claims` with `{"folder": "<content folder>", "limit": 100}` reads the grounded
atoms back; `versum_search` with `{"folder": "<content folder>", "query": "<claim>", "k": 10}`
answers "which sources back this". Shell fallback: the installed engine,
`python -m versum index <folder>` and the other verbs in `references/reference.md`.
Graph writes still route through `loomground-knowledge-write`.

## More

- `references/reference.md` - full inputs, semantics, and guardrails.
- `references/eval.json` - what it wraps, determinism, and test status.
