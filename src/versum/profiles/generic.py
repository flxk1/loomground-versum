"""The ``generic`` profile — a domain-neutral V0 catalogue.

Exists to prove the framework is not law-bound: it carries no legal vocabulary at all,
only general-purpose logical scopes and epistemic modalities. Provisional (V0); widen
only via the same curator-approval gate the closed domains use.
"""
from __future__ import annotations

import re

from ..profile import Profile, register

# general-purpose scholarly identifier schemes (not bound to any single domain)
SOURCE_IDENTIFIERS = (
    ("doi", re.compile(r"\b(10\.\d{4,9}/[-._;()/:a-z0-9]+)\b", re.IGNORECASE)),
    ("arxiv", re.compile(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b")),
)

PREDICATES = frozenset({
    "defines", "asserts", "relates", "causes",
    "enables", "prevents", "supports", "refutes",
})
MODALITIES = frozenset({"asserted", "hypothesized", "definitional", "null"})
QUANTIFICATIONS = frozenset({"universal", "existential", "definite", "count(n)", "null"})
PRINCIPLES: frozenset = frozenset()
CANONS = frozenset({"null"})
INFERENCE_RULES = frozenset({
    "modus_ponens", "analogy", "induction", "abduction", "unspecified",
})

MARKERS = (
    ("is defined as", "defines", "definitional"),
    ("causes", "causes", "asserted"),
    ("means", "defines", "definitional"),
)
QUANT_CUES = (
    ("universal", ("each", "every", "all ", "any ")),
    ("existential", ("at least one", "at least")),
)

PREDICATE_DIMENSIONS = {
    "defines": "structural", "asserts": "relational", "relates": "relational",
    "causes": "causal", "enables": "causal", "prevents": "causal",
    "supports": "relational", "refutes": "relational",
}

PROFILE = Profile(
    id="generic",
    namespace="kg",
    catalogue_version="generic-v0",
    predicates=PREDICATES,
    modalities=MODALITIES,
    quantifications=QUANTIFICATIONS,
    principles=PRINCIPLES,
    canons=CANONS,
    inference_rules=INFERENCE_RULES,
    instrument_rank={},
    markers=MARKERS,
    quant_cues=QUANT_CUES,
    modalities_n=frozenset(),
    def_verbs=frozenset({"means", "is defined as"}),
    source_identifiers=SOURCE_IDENTIFIERS,
    predicate_dimensions=PREDICATE_DIMENSIONS,
)

register(PROFILE)
