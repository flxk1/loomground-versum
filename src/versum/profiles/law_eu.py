"""The ``law-eu`` profile — the EU-law vocabulary for Loomground Versum.

This module is the ONLY place legal catalogue values live. It supplies the closed
axis vocabularies (10 predicates, 7 D + 3 N modalities, 5 quantifications, 12
principles, 5 canons, 12 inference rules), the instrument-rank ladder, the EN + DE
surface-marker tables and the quantification cues, plus the ``dls`` URN namespace.

Provenance: these values were transcribed once, by hand, from an earlier EU-law
research prototype. There is NO code or runtime dependency on that prototype — this
file is self-contained and owns the values. A future amendment is a deliberate edit
here, not a re-import.
"""
from __future__ import annotations

import re

from ..profile import Profile, register

# deterministic identity resolvers for this domain: the EU-law CELEX number first, then
# the general scholarly schemes. The core never names CELEX; it lives here, in the profile.
SOURCE_IDENTIFIERS = (
    ("celex", re.compile(r"celex[\s:_-]*([0-9]{5}[a-z]{1,2}[0-9]{3,4})", re.IGNORECASE)),
    ("doi", re.compile(r"\b(10\.\d{4,9}/[-._;()/:a-z0-9]+)\b", re.IGNORECASE)),
    ("arxiv", re.compile(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b")),
)

# ── Axis 1 — logical form (10 predicates) ────────────────────────
PREDICATES = frozenset({
    "grants", "imposes", "prohibits", "permits", "holds",
    "conditions", "defines", "repeals", "supersedes", "delegates",
})

# ── Axis 2 — deontic modality (7 D + 3 N; union) ─────────────────
MODALITIES_D = frozenset({
    "permitted", "obliged", "prohibited", "exempt", "void", "definitional", "null",
})
MODALITIES_N = frozenset({"recommendation", "proposal", "null"})
MODALITIES = MODALITIES_D | MODALITIES_N

# ── Axis 3 — quantification (5) ──────────────────────────────────
QUANTIFICATIONS = frozenset({
    "universal", "existential", "definite", "count(n)", "null",
})

# instrument classes + rank (load-bearing for lex_superior)
INSTRUMENT_RANK = {
    "treaty:eu": 0, "charter:eu": 0,
    "regulation:eu": 1, "directive:eu": 1, "decision:eu": 1,
    "recommendation:eu": 2, "opinion:eu": 2,
    "case-law:cjeu": None, "case-law:ecthr": None, "case-law:efta-court": None,
}

# ── Axis 4 — purpose (12 principles, 5 canons incl null) ─────────
PRINCIPLES = frozenset({
    "principle:high-level-of-protection", "principle:internal-market-functioning",
    "principle:fundamental-rights", "principle:data-subject-empowerment",
    "principle:transparency", "principle:proportionality", "principle:legal-certainty",
    "principle:effectiveness", "principle:harmonisation", "principle:subsidiarity",
    "principle:effective-remedies", "principle:rule-of-law",
})
CANONS = frozenset({"literal", "teleological", "systematic", "historical", "null"})

# ── Inference rules (11 + closure) ───────────────────────────────
INFERENCE_RULES = frozenset({
    "modus_ponens", "statutory_interpretation:literal",
    "statutory_interpretation:teleological", "statutory_interpretation:systematic",
    "statutory_interpretation:historical", "analogical:eu_law",
    "precedent:cjeu", "precedent:ecthr", "lex_specialis", "lex_posterior",
    "lex_superior", "unspecified",
})

# ── Surface-marker tables — EN + DE (longest patterns first) ─────
MARKERS_EN = (
    ("shall ensure", "imposes", "obliged"),
    ("shall not", "prohibits", "prohibited"),
    ("must not", "prohibits", "prohibited"),
    ("is exempt from", "permits", "exempt"),
    ("has the right to", "grants", "permitted"),
    ("are entitled to", "grants", "permitted"),
    ("is defined as", "defines", "definitional"),
    ("repealed by", "repeals", "void"),
    ("supersedes", "supersedes", "null"),
    ("shall", "imposes", "obliged"),
    ("must", "imposes", "obliged"),
    ("may not", "prohibits", "prohibited"),
    ("may", "permits", "permitted"),
    ("means", "defines", "definitional"),
)
MARKERS_DE = (
    ("darf nicht", "prohibits", "prohibited"),
    ("ist untersagt", "prohibits", "prohibited"),
    ("ist verboten", "prohibits", "prohibited"),
    ("hat das Recht", "grants", "permitted"),
    ("ist berechtigt", "grants", "permitted"),
    ("ist zulässig", "permits", "permitted"),
    ("gilt als", "defines", "definitional"),
    ("bezeichnet", "defines", "definitional"),
    ("im Sinne dieser", "defines", "definitional"),
    ("muss", "imposes", "obliged"),
    ("hat zu", "imposes", "obliged"),
    ("darf", "permits", "permitted"),
    ("kann", "permits", "permitted"),
)
MARKERS = MARKERS_EN + MARKERS_DE

# quantification cue words (Axis 3)
QUANT_CUES = (
    ("universal", ("each", "every", "all ", "any ", "jede", "alle", "jeder")),
    ("existential", ("at least one", "mindestens ein", "at least")),
)

PREDICATE_DIMENSIONS = {
    "grants": "intentional", "imposes": "intentional", "prohibits": "causal",
    "permits": "causal", "holds": "relational", "conditions": "structural",
    "defines": "structural", "repeals": "temporal", "supersedes": "temporal",
    "delegates": "structural",
}

PROFILE = Profile(
    id="law-eu",
    namespace="dls",
    catalogue_version="nd-eu-law-v1",
    predicates=PREDICATES,
    modalities=MODALITIES,
    quantifications=QUANTIFICATIONS,
    principles=PRINCIPLES,
    canons=CANONS,
    inference_rules=INFERENCE_RULES,
    instrument_rank=INSTRUMENT_RANK,
    markers=MARKERS,
    quant_cues=QUANT_CUES,
    modalities_n=MODALITIES_N,
    def_verbs=frozenset({
        "means", "is defined as", "shall mean",
        "bezeichnet", "gilt als", "im sinne dieser",
    }),
    source_identifiers=SOURCE_IDENTIFIERS,
    predicate_dimensions=PREDICATE_DIMENSIONS,
)

register(PROFILE)

# ── self-check against doc-stated counts ─────────────────────────
assert len(PREDICATES) == 10
assert len(MODALITIES_D) == 7 and len(MODALITIES_N) == 3
assert len(QUANTIFICATIONS) == 5
assert len(PRINCIPLES) == 12
assert len(CANONS) == 5
assert len(INFERENCE_RULES) == 12
