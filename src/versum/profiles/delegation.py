"""The ``delegation`` profile — vocabulary for authority, purpose and onward transfer.

A delegation is stated somewhere before it is exercised: in an engagement letter, a
policy, a ticket, a data-processing agreement. This profile lets those statements be
read as ordinary span claims — anchored to exact offsets of an exact source, drawn
from a closed vocabulary, checked by the same invariants as any other claim.

Why that matters more here than elsewhere. A purpose asserted at runtime cannot be
checked by a supervisor or reconstructed by a later reviewer; a purpose anchored to
the document that conferred it can be checked by anyone holding the document. The
comparison a divergence detector makes — did this trajectory serve the purpose it was
given? — is only as good as the record of the second term, and this profile is how
that term gets a source.

``mandates`` and ``restricts`` project onto the **intentional** dimension, which is
the Federation-5D axis for purpose; ``revokes`` projects onto **causal**, because
revoking changes a position rather than describing one.

Nothing here reasons. The profile supplies vocabulary and surface cues; whether a
trajectory diverged from a mandate is a judgement for a consumer, and this engine
deliberately refuses it.

Provisional (V0), like ``generic``: widen only through the same curator-approval gate
the closed domains use.
"""
from __future__ import annotations

import re

from ..profile import Profile, register

# No domain identifier scheme: a mandate lives in whatever document conferred it,
# and the write guard falls to the path-slug rather than inventing a URN scheme.
SOURCE_IDENTIFIERS: tuple = ()

PREDICATES = frozenset({
    "mandates",     # confers a purpose: what the authority is *for*
    "delegates",    # confers authority on another, who acts on the delegator's behalf
    "authorises",   # states what the holder may do
    "restricts",    # narrows a purpose or a permitted use
    "consigns",     # releases material onward to a named recipient
    "revokes",      # withdraws authority previously conferred
})
MODALITIES = frozenset({"asserted", "hypothesized", "definitional", "null"})
QUANTIFICATIONS = frozenset({"universal", "existential", "definite", "count(n)", "null"})
PRINCIPLES: frozenset = frozenset()
CANONS = frozenset({"null"})
INFERENCE_RULES = frozenset({
    "modus_ponens", "analogy", "induction", "abduction", "unspecified",
})

# Surface cues, deliberately conservative: an unrecognised phrasing yields no claim,
# which is the honest outcome. A wrongly-typed mandate would misstate what an actor
# was authorised to achieve, and that is silently-wrong territory.
MARKERS = (
    ("on behalf of", "delegates", "asserted"),
    ("acting for", "delegates", "asserted"),
    ("appoints", "delegates", "asserted"),
    ("for the purpose of", "mandates", "asserted"),
    ("for the purposes of", "mandates", "asserted"),
    ("in order to", "mandates", "asserted"),
    ("is authorised to", "authorises", "asserted"),
    ("is authorized to", "authorises", "asserted"),
    ("is instructed to", "authorises", "asserted"),
    ("solely for", "restricts", "asserted"),
    ("only for", "restricts", "asserted"),
    ("and for no other purpose", "restricts", "asserted"),
    ("must not be used for", "restricts", "asserted"),
    ("is disclosed to", "consigns", "asserted"),
    ("is transferred to", "consigns", "asserted"),
    ("shall be provided to", "consigns", "asserted"),
    ("revokes", "revokes", "asserted"),
    ("withdraws", "revokes", "asserted"),
    ("terminates the appointment", "revokes", "asserted"),
)

QUANT_CUES = (
    ("universal", ("each", "every", "all ", "any ")),
    ("existential", ("at least one", "at least")),
)

# Local predicate -> universal Federation-5D edge dimension. Purpose is intentional;
# a revocation acts on a position, so it is causal; the rest relate parties.
PREDICATE_DIMENSIONS = {
    "mandates": "intentional",
    "restricts": "intentional",
    "delegates": "relational",
    "authorises": "relational",
    "consigns": "relational",
    "revokes": "causal",
}

PROFILE = Profile(
    id="delegation",
    namespace="dlg",
    catalogue_version="delegation-v0",
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
