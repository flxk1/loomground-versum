"""The ``scholarly`` profile — an academic / prose vocabulary for non-law domains.

Non-law domains (philosophy, computer science, economics, the sciences) are NOT norms:
their claims are *assertions, definitions, causal and evidential relations* — not deontic
obligations. Running them through the legal ``law-eu`` profile mis-stamps every claim with
legal predicates (imposes/permits/prohibits), which then corrupts concept identity in the
canon. This profile stamps the neutral scholarly axes instead (defines / asserts / relates /
causes / enables / prevents / supports / refutes) with a rich bilingual (EN+DE) surface-marker
table so it actually fires on academic prose — the missing piece in the sparse ``generic`` V0.

This is a PROFILE, so domain vocabulary is allowed here (only the CORE stays neutral).
Provisional (V0); widen only via the same curator-approval gate the closed domains use.
"""
from __future__ import annotations

import re

from ..profile import Profile, register

# scholarly works are identified by DOI / arXiv, not a legal instrument scheme
SOURCE_IDENTIFIERS = (
    ("doi", re.compile(r"\b(10\.\d{4,9}/[-._;()/:a-z0-9]+)\b", re.IGNORECASE)),
    ("arxiv", re.compile(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b")),
)

# ── Axis 1 — scholarly predicates (what the claim does) ──────────
PREDICATES = frozenset({
    "defines", "asserts", "relates", "causes",
    "enables", "prevents", "supports", "refutes",
})

# ── Axis 2 — epistemic modality (stance of the claim) ────────────
# asserted = stated as fact; hypothesized = tentative/conjectural; definitional = a definition.
MODALITIES = frozenset({"asserted", "hypothesized", "definitional", "null"})
# a hypothesis is the author's conjecture (speaker-flagged) → normative-side polarity (N);
# asserted facts and definitions read as descriptive (D).
MODALITIES_N = frozenset({"hypothesized"})

# ── Axis 3 — quantification (shared neutral shape) ───────────────
QUANTIFICATIONS = frozenset({"universal", "existential", "definite", "count(n)", "null"})

PRINCIPLES: frozenset = frozenset()
CANONS = frozenset({"null"})
INFERENCE_RULES = frozenset({
    "modus_ponens", "analogy", "induction", "abduction", "unspecified",
})

# ── Surface markers (longest / most specific first) ──────────────
# (pattern, predicate, modality). Bilingual EN+DE. The extractor matches case-insensitively
# and keys one item per (predicate, sentence), so near-synonyms map to the same predicate.
MARKERS = (
    # defines
    ("is defined as", "defines", "definitional"),
    ("we define", "defines", "definitional"),
    ("refers to", "defines", "definitional"),
    ("is defined", "defines", "definitional"),
    ("denotes", "defines", "definitional"),
    ("definiert als", "defines", "definitional"),
    ("bezeichnet", "defines", "definitional"),
    ("bedeutet", "defines", "definitional"),
    ("means", "defines", "definitional"),
    # asserts
    ("we argue that", "asserts", "asserted"),
    ("we claim that", "asserts", "asserted"),
    ("we show that", "asserts", "asserted"),
    ("we find that", "asserts", "asserted"),
    ("it follows that", "asserts", "asserted"),
    ("demonstrates that", "asserts", "asserted"),
    ("shows that", "asserts", "asserted"),
    ("argues that", "asserts", "asserted"),
    ("holds that", "asserts", "asserted"),
    ("wir argumentieren", "asserts", "asserted"),
    ("wir zeigen", "asserts", "asserted"),
    ("zeigt, dass", "asserts", "asserted"),
    # hypothesized (tentative)
    ("we hypothesize", "asserts", "hypothesized"),
    ("we conjecture", "asserts", "hypothesized"),
    ("suggests that", "asserts", "hypothesized"),
    ("may indicate", "asserts", "hypothesized"),
    ("might", "asserts", "hypothesized"),
    ("vermutlich", "asserts", "hypothesized"),
    # relates
    ("is associated with", "relates", "asserted"),
    ("correlates with", "relates", "asserted"),
    ("is related to", "relates", "asserted"),
    ("depends on", "relates", "asserted"),
    ("corresponds to", "relates", "asserted"),
    ("hängt ab von", "relates", "asserted"),
    ("korreliert mit", "relates", "asserted"),
    # causes
    ("gives rise to", "causes", "asserted"),
    ("leads to", "causes", "asserted"),
    ("results in", "causes", "asserted"),
    ("causes", "causes", "asserted"),
    ("produces", "causes", "asserted"),
    ("führt zu", "causes", "asserted"),
    ("verursacht", "causes", "asserted"),
    ("bewirkt", "causes", "asserted"),
    # enables
    ("makes possible", "enables", "asserted"),
    ("enables", "enables", "asserted"),
    ("allows", "enables", "asserted"),
    ("facilitates", "enables", "asserted"),
    ("ermöglicht", "enables", "asserted"),
    ("erlaubt", "enables", "asserted"),
    # prevents
    ("rules out", "prevents", "asserted"),
    ("prevents", "prevents", "asserted"),
    ("precludes", "prevents", "asserted"),
    ("inhibits", "prevents", "asserted"),
    ("verhindert", "prevents", "asserted"),
    ("schließt aus", "prevents", "asserted"),
    # supports
    ("is evidence for", "supports", "asserted"),
    ("is consistent with", "supports", "asserted"),
    ("supports", "supports", "asserted"),
    ("confirms", "supports", "asserted"),
    ("corroborates", "supports", "asserted"),
    ("stützt", "supports", "asserted"),
    ("bestätigt", "supports", "asserted"),
    # refutes
    ("is inconsistent with", "refutes", "asserted"),
    ("contradicts", "refutes", "asserted"),
    ("refutes", "refutes", "asserted"),
    ("challenges", "refutes", "asserted"),
    ("undermines", "refutes", "asserted"),
    ("widerlegt", "refutes", "asserted"),
    ("widerspricht", "refutes", "asserted"),
)

QUANT_CUES = (
    ("universal", ("every", "all ", "each", "any ", "always", "jede", "alle")),
    ("existential", ("at least", "some ", "there exists", "mindestens")),
)

PREDICATE_DIMENSIONS = {
    "defines": "structural", "asserts": "relational", "relates": "relational",
    "causes": "causal", "enables": "causal", "prevents": "causal",
    "supports": "relational", "refutes": "relational",
}

PROFILE = Profile(
    id="scholarly",
    namespace="sch",
    catalogue_version="scholarly-v0",
    predicates=PREDICATES,
    modalities=MODALITIES,
    quantifications=QUANTIFICATIONS,
    principles=PRINCIPLES,
    canons=CANONS,
    inference_rules=INFERENCE_RULES,
    instrument_rank={},
    markers=MARKERS,
    quant_cues=QUANT_CUES,
    modalities_n=MODALITIES_N,
    def_verbs=frozenset({"means", "is defined as", "refers to", "denotes",
                         "definiert als", "bezeichnet"}),
    source_identifiers=SOURCE_IDENTIFIERS,
    predicate_dimensions=PREDICATE_DIMENSIONS,
)

register(PROFILE)
