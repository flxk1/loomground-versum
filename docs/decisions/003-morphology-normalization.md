# ADR-003: Morphology normalization for key_term identity

**Status:** Accepted
**Date:** 2026-07-18
**Deciders:** engine owner

## Context

A concept's coordinate is axis-signature + `key_term`. Inflected surface forms of the same
term mint *different* coordinates, so one concept fragments: on real claims,
`digitalen-produkts` / `digitale-produkt` / `digitalen-produkten` are all "digital product"
but became three concepts. This is the morphology input to concept quality (ADR-002 covered
spacing; per-domain profiles is the third). The corpus is bilingual (DE-dominant legal + EN).

Constraints: deterministic (no model, no network), engine stays domain-neutral (morphology is
*language* structure, not a domain — the same category as the function-word lists already in
core), and reversible/opt-in (must not silently change identities unless enabled).

## Decision

Add `versum/concept/morph.py`: `normalize(term_slug, language)` stems each word of a key_term slug so
inflected variants converge to one identity. Two backends: **Snowball** (`snowballstemmer`,
pure-python, offline, deterministic — the primary when a language is configured) and a
**dependency-free conservative suffix normalizer** (multilingual, used when Snowball or the
language is unavailable). In the canon, the **normalized** form keys the concept_id while the
**label keeps the most frequent surface form** among the variants it merged, so identity
converges without losing readability. Off by default (`morph_language: null`); the user opts
in per curation run via config.

## Options Considered

### A: No normalization (status quo)
Simple; but concepts fragment across declensions — the defect we're fixing.

### B: Hand-rolled multilingual suffix stripper only
| Complexity | Low | Accuracy | Medium | Dependency | none |

Strips a small ordered set of DE/EN endings (`s, es, e, en, n, er, …`) with a min-stem guard.
No dependency, language-neutral, but over/under-stems on irregulars.

### C: Snowball stemmer, language-configured (CHOSEN, with B as fallback)
| Complexity | Low-Med | Accuracy | High | Dependency | snowballstemmer (pure-python, offline) |

Gold-standard deterministic stemming; needs a configured language. Falls back to B when the
language is unset or the package is missing, so the engine still runs dependency-free.

### D: Full lemmatization (spaCy/dictionary)
Rejected: heavy models, non-trivial determinism, offline burden — disproportionate to keying a
concept id.

## Trade-off Analysis

Identity only needs *consistency*, not linguistic perfection: any stemmer that maps variants to
a common form converges them, and because the label keeps the surface form, over-stemming's
only cost is a coarser id (a real risk = *false merges* of distinct terms). So the design is
tuned conservatively and the adversarial loop hunts false merges (distinct terms → one id) and
misses (variants not merged). Snowball gives the best accuracy where a language is known;
fallback B keeps the no-dependency, language-agnostic path alive.

## Backend precision (from adversarial review)

Adversarial testing surfaced the precision/recall split between the two backends:

- The **fallback (`"auto"`)** was first too aggressive — stripping derivational `-er` merged
  `provider`/`provide`, `server`/`serve`; stripping `-ung*` over-stemmed. Fixed by restricting
  the suffix set to clear **inflectional** endings (`es/en/e/s`) only. It now keeps agent
  nouns distinct from verbs while still converging plurals (`leistungen`→`leistung`,
  `obligations`→`obligation`) and case forms (`produkts/produkten/produkte`→`produkt`).
  **This is the recommended default** — precise, dependency-free, language-agnostic.
- The **Snowball backend (`morph_language:"german"` etc.)** is inherently more aggressive: it
  will false-merge some distinct lexemes (`Wette`/`Wetter`→`wett`, `Mahl`/`mahlen`→`mahl`,
  `Gläubiger`/`Gläubige`→`gläubig`). Use it only where its higher recall is worth that cost;
  it is opt-in, never the default. (Note: several umlaut cases the stemmer would merge don't
  actually reach the concept id, because the key_term slug splits umlauts before morph runs —
  but the non-umlaut merges are real.)

## Consequences

- **Easier:** declension variants collapse; the canon fragments less; junk from inflection drops.
- **Harder:** a language must be chosen per run for best results; cross-language terms don't
  merge (correct — they're different words). False-merge risk is the thing to watch.
- **Revisit:** whether bilingual corpora need per-term language detection; the fallback's
  suffix set after seeing real merges.

## Action Items
1. [ ] `versum/concept/morph.py` (Snowball + conservative fallback), config `morph_language`.
2. [ ] Wire into `build_canon`: normalized form → id, modal surface form → label.
3. [ ] Tests + verify on staged real claims (produkt* collapses); adversarial false-merge loop.
