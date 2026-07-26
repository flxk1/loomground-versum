"""The ``news`` profile — a lightweight event/fact vocabulary for news signals.

Distinct from the legal deontic 5D (``law-eu``): news claims are *who-did-what-when*
events, not norms. The predicate axis names reporting acts (announced / proposed /
enacted / ruled / fined / launched / published / withdrawn); the modality axis carries
reporting stances (asserted / reported / null) rather than deontic force; polarity is
present (every extracted event is stamped, all descriptive here — no reporting stance
carries normative polarity). Its own ``news`` namespace keeps its URN space separate.

This is a PROFILE, so domain vocabulary is allowed here (only the CORE must stay neutral).
Provisional (V0); widen only via the same curator-approval gate the closed domains use.
"""
from __future__ import annotations

import re

from ..profile import Profile, register

# News signals are dated event reports; no scholarly/legal identifier scheme is baked in.
SOURCE_IDENTIFIERS: tuple = ()

# ── Axis 1 — event predicates (who did what) ─────────────────────
PREDICATES = frozenset({
    "announced", "proposed", "enacted", "ruled",
    "fined", "launched", "published", "withdrawn",
})

# ── Axis 2 — reporting modality (stance of the signal) ───────────
MODALITIES = frozenset({"asserted", "reported", "null"})
# No reporting stance carries normative polarity — news is descriptive; polarity stays 'D'.
MODALITIES_N: frozenset = frozenset()

# ── Axis 3 — quantification (shared neutral shape) ───────────────
QUANTIFICATIONS = frozenset({"universal", "existential", "definite", "count(n)", "null"})

PRINCIPLES: frozenset = frozenset()
CANONS = frozenset({"null"})
INFERENCE_RULES = frozenset({"unspecified"})

# ── Surface markers (longest / most specific first) ──────────────
MARKERS = (
    ("announced", "announced", "reported"),
    ("proposed", "proposed", "reported"),
    ("has enacted", "enacted", "asserted"),
    ("enacted", "enacted", "asserted"),
    ("ruled", "ruled", "asserted"),
    ("fined", "fined", "asserted"),
    ("launched", "launched", "reported"),
    ("published", "published", "asserted"),
    ("withdrew", "withdrawn", "asserted"),
    ("withdrawn", "withdrawn", "asserted"),
)

QUANT_CUES = (
    ("universal", ("every", "all ", "each")),
    ("existential", ("at least", "at least one")),
)

PREDICATE_DIMENSIONS = {
    "announced": "relational", "proposed": "intentional", "enacted": "temporal",
    "ruled": "relational", "fined": "causal", "launched": "temporal",
    "published": "temporal", "withdrawn": "temporal",
}

PROFILE = Profile(
    id="news",
    namespace="news",
    catalogue_version="news-v0",
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
    def_verbs=frozenset(),
    source_identifiers=SOURCE_IDENTIFIERS,
    predicate_dimensions=PREDICATE_DIMENSIONS,
)

register(PROFILE)
