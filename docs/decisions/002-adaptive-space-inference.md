# ADR-002: Adaptive per-line space inference in the PDF extractor

**Status:** Accepted
**Date:** 2026-07-18
**Deciders:** engine owner

## Context

The extractor calls `pdfplumber` `page.extract_text()`, which inserts a space between two
characters only when their horizontal gap exceeds a threshold `x_tolerance` (default **3 pt,
absolute**). Real corpus PDFs — justified bilingual (DE/EN) legal text — routinely have
inter-word gaps **below** that threshold, so words merge on extraction
(`derAnspruchaufHerstellungdesdigitalenProdukts…`). This "lost spaces" artifact then poisons
every downstream layer: claim text is corrupted, and the coordinate-identity canon fragments
one concept across many coordinates (`digitalen-produkts` / `digitale-produkt` /
`digitalen-produkten`) and mints junk key_terms.

Measured on reproductions (in-container, `pdfplumber` 0.11.9, glyph geometry inspected):

- Tight/merged lines: intra-word gaps ≈ **0 pt**, inter-word gaps ≈ **1 pt** — cleanly
  bimodal but small in absolute terms, which is exactly why a 3 pt threshold misses them.
- Loose/tracked lines (justified text, letter-spacing): intra-word gaps ≈ tracking (1–3 pt),
  inter-word gaps ≈ tracking + space (4–6 pt) — also bimodal, but larger.

**Forces:** the two failure modes are in *tension*. A lower global threshold fixes tight
merging but **shatters** tracked words (`V e r h a e l t n i s…`); the default shatters
nothing but merges tight text. No single global `x_tolerance` (absolute or font-ratio) wins
on both — verified empirically.

**Constraints:** engine core must stay domain- and language-neutral (no vocabulary, no
dictionary word-splitting), deterministic (no model, no `Date.now`/random), and reversible in
delivery (re-extraction writes new outputs, never mutates source PDFs). The real PDFs live on
the user's device and are never fetched in-session; the fix must be verifiable on synthetic
reproductions here and re-run on-device.

## Decision

Replace the single global-threshold call with **per-line adaptive space inference driven by
the line's own glyph-gap distribution.** For each text line: if `pdfplumber` already emitted
space glyphs, trust the line unchanged; otherwise compute inter-glyph gaps and find the
**largest natural break** in the sorted gap distribution (a 1-D Jenks-lite split). If that
break is significant (a clean positive separation, gated against font size), insert spaces at
gaps on the wide side of the break; if the gaps are uniform (a single word / no detectable
break), leave the line untouched. All thresholds are geometry-relative to the line's median
glyph size and **config-tunable**, never hardcoded per machine.

This is content-geometry, not vocabulary: it names no domain value, needs no model, and is a
pure deterministic function of glyph coordinates.

## Options Considered

### Option A: Lower global `x_tolerance` (absolute)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Correctness | **Fails** — shatters tracked text; not font-scale aware |
| Neutrality | OK |

**Pros:** one-line change. **Cons:** trades merging for shattering; absolute pt threshold is
wrong across font sizes.

### Option B: `x_tolerance_ratio` (font-relative global)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Correctness | **Fails** — a ratio that fixes tight merging (≈0.05) still shatters tracked words whose tracking exceeds it |
| Neutrality | OK |

**Pros:** font-scale aware, uses pdfplumber's own machinery. **Cons:** still a single global
knob; the tension is fundamental, so it cannot satisfy both regimes.

### Option C: Per-line adaptive natural-break (CHOSEN)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium |
| Correctness | Handles tight + tracked + normal + headings + single-word + numeric in reproductions |
| Neutrality | Geometry only; no vocabulary; deterministic |

**Pros:** adapts to each line's own regime; splits at true word boundaries in both tight and
tracked text; leaves clean/uniform lines untouched. **Cons:** more code and edge cases (single
glyph, mixed-size lines, RTL) — mitigated by a synthetic-PDF test battery and adversarial
verification.

### Option D: Dictionary word-segmentation (wordninja-style) on merged tokens
Rejected: language-dependent (breaks the neutrality invariant), lossy, and non-deterministic
across dictionaries. Some truly zero-gap PDFs are unrecoverable by *any* geometry; those are
reported, not guessed at.

## Trade-off Analysis

The decision trades a small amount of extractor complexity for correctness across both
failure regimes, without importing any language model or dictionary. Global-threshold options
(A, B) are simpler but provably cannot resolve the tight-vs-tracked tension. Option C keeps
the core neutral and deterministic while being adaptive where it must be — per line. Truly
zero-gap concatenation (no geometric signal at all) remains out of scope and is surfaced
honestly rather than mangled.

## Consequences

- **Easier:** claim text quality improves at the source; the canon fragments far less; junk
  key_terms from mangled spacing drop out.
- **Harder:** the extractor now reasons about glyph geometry; edge cases need test coverage
  (the battery). Thresholds are tunable, so a bad corpus can be re-tuned via config, not code.
- **Revisit:** the significance gate constants after seeing the full-corpus re-extraction;
  whether some domains still need per-domain tuning; whether zero-gap PDFs warrant a separate
  reported bucket.
- **Cost:** re-extraction over the ~6,913 PDFs must be re-run on-device (like the migration);
  curation re-run follows. Both are already resumable/parallel runners.

## Known limitations (from adversarial review)

Two failure modes survive, both a **fundamental geometric ambiguity** rather than a fixable
bug: a letter-*tracked* word and a *spaced-out* sequence of single characters are identical in
glyph geometry, so no local rule separates them.

- **Uniformly spaced lines** (a single letter-tracked word, digit rows `1 2 3 4`, spaced
  initials, German *Sperrsatz* headings `G R U N D R E C H T E`). No gap exceeds
  baseline+margin, so the threshold is `None` and the glyphs are joined unchanged — the word
  is never shattered, and the result matches the pre-fix behaviour byte-for-byte. For
  *Sperrsatz* the join (`GRUNDRECHTE`) is usually the *correct* word; for a bare numeric row it
  is not, but recovering that would need word semantics, not geometry. (An early majority-split
  *guard* was tried and removed: it wrongly merged short legitimate lines like `5 zu 3` while
  the `None`-threshold path already covers the uniform case.)
- **A single line mixing two letter-spacing regimes at the same font size** (e.g. a 2.5 pt
  letter-tracked word immediately followed by tightly-kerned words, no space glyphs). One
  per-line baseline cannot serve both, so the tracked word may over-split (`CODE`→`C O D E`) or
  a tighter run may under-split. Rare and constructed; because both runs share a font size it
  is not separable by cheap per-run segmentation. Documented and left; whole-line tracked
  headings (the common case) are handled by the `None`-threshold path above.

Truly zero-gap concatenation (glyphs with no positional gap at all) remains unrecoverable by
any geometry and is left as-is rather than guessed at.

## Action Items
1. [ ] Implement per-line adaptive inference in `versum/io/extract.py` (config-tunable), keep the NUL/control hygiene.
2. [ ] Synthetic-PDF test battery: tight, loose-tracked, normal, heading, single-word, numeric, multi-size; + neutrality guard.
3. [ ] Adversarial verification (no regression on clean text; no spurious splits; determinism).
4. [x] `scripts/operations/reextract_full.py` config-driven resumable runner; deliver bundle + runbook; then re-run curation.
