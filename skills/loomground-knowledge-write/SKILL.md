---
name: loomground-knowledge-write
description: The Versum-facing alias for the single write path into a Loomground knowledge graph. Use when an approved local PDF or prepared source record should be added. Delegates every executable write to loomground-editorial's live capture-to-kg writer; it has no second identity, deduplication, sidecar, or persistence implementation. It NEVER fetches binaries from within a session.
---

# loomground-knowledge-write

The Versum-facing name for the sanctioned `capture-to-kg` write door. It is an alias,
not another writer: every executable request is forwarded to the live editorial
helper, which owns identity, deduplication, stub/sidecar production, and the capture
report.

## How it runs — explicit delegation, not an LLM

Run:

```bash
python3 <this-skill>/scripts/delegate_capture.py \
  --spec /tmp/kg_spec.json \
  --outdir /tmp/kg_drop \
  --registry "<kg-root>/knowledge_index/source_registry.csv"
```

The adapter resolves
`loomground-editorial/skills/capture-to-kg/scripts/kg_capture.py`, then forwards the
canonical CLI arguments unchanged. In an installed layout, set
`LOOMGROUND_CAPTURE_TO_KG_SCRIPT` to that file. If it cannot be resolved, the adapter
fails closed without creating an output directory. There is deliberately no fallback
to `versum/write.py`.

## When to use

- The editorial pipeline showed sources and the user approved one or more for the graph.
- The user supplies a local PDF or prepared source record to capture.
- The user drops a PDF and says "add this to the knowledge graph / KG / Versum."

Do NOT use it to invent or guess a citation, and do NOT confirm concepts — this skill
writes the provenance + candidate-claim layers only; concept links are curation.

## Inputs

- **spec** — a `{"sources": [...]}` JSON document using the canonical `capture-to-kg`
  source fields. A local PDF may be supplied as `pdf_path`; URLs and identifiers are
  provenance metadata, not an invitation for this adapter to fetch bytes.
- **outdir** — staging directory for the inbox artifacts.
- **registry** — optional `source_registry.csv` used by the canonical writer for dedup.

## Steps

1. **Resolve the citation.** Use the known-correct citation from the local record. For a PDF,
   read its metadata / first page. If the citation cannot be verified, stop rather than guess.
2. **Compute the canonical URN.** Prefer a canonical identifier embedded in the record —
   `urn:dls:celex:...`, `urn:dls:doi:...`, `urn:dls:arxiv:...`. Fall back to a
   path/title slug `urn:<namespace>:source:<slug>`. (The folder indexer uses the slug
   form; a canonical identifier, when known, is authoritative and recorded in the
   sidecar so `generate_index` honours it.)
3. **Dedup.** Check the source registry for a match by URN, by identifier, and by title.
   On a hit, report the existing entry and stop rather than double-writing.
4. **Write the house record.** Create the house-format stub `YYYY-author-title.md` and a
   `.md.metadata.json` sidecar carrying the resolved citation, the canonical URN, the
   verification level, and (if applicable) the `sidecar_canonical` override.
5. **PDF placement — never fetched in-session.** Put an already-present local PDF path in
   the canonical spec. Otherwise record the URL/status honestly; acquisition remains
   out-of-band.
6. **Delegate the write.** Invoke `delegate_capture.py`; do not invoke
   `versum capture` as an alternative persistence door.
7. **Report.** Return the canonical capture report: URN, written artifacts, duplicate
   status, kind, and PDF status. Indexing/organizing remains the downstream KG step.

## Guardrails

- Provenance is single-history: never rewrite an existing source's URN by hand; a URN
  change is a deliberate sidecar override, cascaded by re-indexing.
- Candidate-only: this skill never confirms axes or mints concepts — that is the
  curation step.
- Contract-preserving: this alias does not reinterpret the canonical writer's namespace
  or schema.
- No in-session fetching: never pull a PDF (or any binary) over the network from within
  a session — no curl / urllib / web-fetch bypass. Binaries arrive out-of-band only.
- Sit on top of the existing KG, don't duplicate it: where a Digital Law Sources stub /
  sidecar / registry already exists for a source, consume it — reuse its URN and
  sidecar rather than re-minting a parallel provenance record.

## Relationship to loomground-editorial

`loomground-editorial` owns the write leg in `capture-to-kg`. This skill provides the
Versum-facing vocabulary and delegates to that live implementation after approval.
