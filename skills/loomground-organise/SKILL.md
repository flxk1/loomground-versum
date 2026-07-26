---
name: loomground-organise
description: Organise documents into a Loomground Versum by shared mental models, with a person confirming every placement. Use when the user wants to triage the review queue, file a new document, or re-shelve an existing one into the right library/domain/year — "organise the Versum", "sort my inbox", "where does this document belong", "clear the review queue", "suggest a domain for this". It ranks candidate domains and the nearest existing sources by concept-overlap (the document's mental-model neighbours), shows that evidence, and — only after a human confirms — hands the write to loomground-knowledge-write. It never auto-files and never invents a domain; low-overlap or novel items stay in the review queue.
---

# loomground-organise

The organiser sits between intake and the graph. Intake (the inbox passes) has already
given a document a stable URN, a year, and a place in the review queue. This skill decides
**where it belongs** — and it does that the way the corpus is actually structured: by the
mental models a document shares with the corpus, not by a keyword guess. It proposes; a
person disposes; the write goes through the one door.

## The rule this skill exists to enforce

Placement is a **suggestion a human confirms**, never an automatic filing. Measured on the
current corpus, ranking a document by its concept-overlap puts the correct domain in the
top-3 candidates about four times in five — excellent as evidence for a person, not safe as
an autopilot. So this skill surfaces the ranked evidence and stops; the human (or an LLM
acting with the human's confirmation) picks. Anything with no clear mental-model neighbour
stays in the review queue rather than being filed on a guess.

## Effort ladder — local-first, cascade up

Spend the least model power that settles the placement. Every rung still ends in a human
confirming; the ladder only decides *who drafts the proposal*.

- **Easy → regex / deterministic (no model).** Canonical id (CELEX / DOI / arXiv), year, dedup,
  and the concept-overlap ranking are pure computation. When the ranking shows one dominant
  neighbour domain (`recommended_tier: regex`), the deterministic suggestion is enough to put
  in front of a person — no model call.
- **Medium → local LLM (if available).** When several domains sit close together, or the shared
  concepts read like discourse filler rather than mental models (`recommended_tier: local-llm`),
  a local model reads the document and the ranked evidence and drafts the call. Local first,
  always — the corpus may be sensitive and the local path never leaves the machine.
- **Hard → cloud LLM (only on the user's preference).** A genuinely novel document (no
  mental-model neighbour, high mint-rate), a real multi-domain judgement, or minting a new
  domain (`recommended_tier: cloud-llm`) may warrant the strongest reader — but cloud is
  opt-in per the user's privacy/cost preference. If the user has not opted in, or the material
  is marked local-only, do not escalate to cloud: keep the item in review for a person instead.

The cascade is the DEFAULT, not a cage. It is set by an effort policy the user owns.

## Configuring the effort policy

The policy lives in a small JSON file in the workspace (data side, under `Knowledge/`, not the
engine repo). `organise.py suggest --config <path>` reads it; with no config the default cascade
applies. `mode` is the dial:

- `cascade` — cheapest sufficient tier by evidence (the default).
- `cloud` — the cloud model drafts every placement (for users with tokens to spend who want the
  strongest reader on everything; the mode itself is the cloud opt-in).
- `local` — a local model drafts every placement; nothing leaves the machine.
- `deterministic` — no model at all; the deterministic suggestion goes straight to a person.

In `cascade`, `allow_cloud` gates escalation to the cloud (a privacy/cost opt-in) and
`local_available` says whether a local model is wired; `dominance` / `min_signal` tune the
routing. See `organise.config.example.json`.

**If no policy file exists, ask the user once** which mode they want (everything-cloud,
local-first cascade, local-only, or deterministic) and their cloud opt-in, then write it with
`organise.py config <path> --init` (edit the values to match their answer) so the choice
persists. Don't assume a default silently for a user who has tokens and wants the LLM on
everything — the whole point is that this is their call.

`organise.py suggest` emits `recommended_tier` (and `effort_mode`) so the routing is explicit.
The thresholds behind the cascade are tunable hints, never filing gates — they file nothing and
should be calibrated against the score distribution, not trusted as-is.

## How it runs

Two deterministic helpers do the mechanical work; the model does the judgement.

- `python scripts/organise.py list --review <review_dir>` — show what is waiting, read from
  each item's `*.metadata.json` provenance sidecar (URN, year, provenance level).
- `python scripts/organise.py suggest --store <kg_root> --concepts <c1,c2,...>` — rank the
  candidate domains and the nearest existing sources for a document's concept set, by
  rarity-weighted (IDF) concept overlap. Use `--urn <urn>` instead to re-rank a source that
  is already indexed (leave-one-out).

A document's concept set comes from the engine extractor — run a capture/sync on the item
first so it has concepts to rank on. This skill reads and ranks; it does not extract and it
does not write.

## Inputs

- **review_dir** — the workspace review queue (data side, under the `Knowledge` workspace).
- **kg_root** — the by-domain store to rank against (holds `by-domain/<domain>/concepts.csv`).
- **the document** — so the model can read it and weigh the ranked evidence against the text.

## Steps

1. **List the queue.** Run `organise.py list` to see the waiting items and their URNs/years.
2. **Get the evidence.** For an item, run `organise.py suggest` with its extracted concepts.
   You get ranked candidate domains (each with its nearest source) and the closest sources
   overall. Read the document alongside this — the ranking is grounding, not a verdict.
3. **Weigh mint-rate.** If the item grounds mostly NEW concepts (high mint-rate / few shared
   neighbours), treat it as genuinely novel: keep it in review, do not force a domain. High
   overlap with one domain's sources is a confident suggestion; a split across domains is a
   real multi-domain signal to raise with the person.
4. **Propose and confirm.** Present the top candidate(s), the year from the sidecar, and the
   nearest sources as the reason. Ask the person to confirm the domain, pick another, or mint
   a new domain (minting is a deliberate act, not a fallback). Never file without confirmation.
5. **Write through the one door.** On confirmation, hand off to `loomground-knowledge-write`
   with the confirmed target folder/profile. That skill owns identity, dedup, sidecar, and
   indexing; this skill does not re-implement any of it.
6. **Leave a trail.** The write is logged and reversible by the write path; if a person later
   disagrees, re-run `suggest` and re-file — placement is a projection, not a one-way move.

## What this skill must not do

- Auto-file, or file anything without a person's confirmation.
- Invent a domain, or mint a new domain to avoid the review queue.
- Name a domain vocabulary in code — the domains come from the store, not from this skill.
- Write to the graph directly — every write is the loomground-knowledge-write path.
- Trust a suggestion built on discourse-filler concepts; if the shared concepts look like
  stopword fragments rather than mental models, say so and fall back to review.
