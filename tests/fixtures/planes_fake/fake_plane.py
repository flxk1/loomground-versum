"""A FAKE plane descriptor for versum's plane tests (contract v1).

Its vocabulary is invented and belongs to no real Loomground plane. Like a real plane it
never imports the versum. Rules (deterministic, pure):

* a sentence containing "shout" -> relation ``shouts`` over the whole sentence, with the
  closed-vocabulary coordinate ``tone = loud`` bound to the ``clause.voice`` slot;
* a sentence containing " that " -> relation ``nests`` over the embedded clause after it
  (its own sub-span), ``tone = calm``; when the sentence also shouts, the ``shouts`` claim
  links to the embedded clause with a ``temporal`` link;
* ``context["source"]["mood"]``, when given, is copied onto every claim's ``mood`` axis.
"""
from __future__ import annotations

PLANE_ID = "fakeplane"
VERSION = "0.0.1-test"


def nd_system() -> dict:
    return {
        "id": "fakeplane-system",
        "namespace": "fakeplane.test",
        "version": VERSION,
        "axes": {
            "tone": {"value_type": "controlled_identifier", "vocabulary_mode": "closed",
                     "vocabulary": ["calm", "loud"], "cardinality": "one"},
            "mood": {"value_type": "string", "vocabulary_mode": "open"},
        },
        "bindings": [{"form_slot": "clause.voice", "allowed_axes": ["tone"],
                      "required": False}],
        "validation": {"unknown_values": "reject"},
    }


BINDING = {"shouts": "intentional", "nests": "relational", "tone": "causal"}


def _clause(sentence: str):
    i = sentence.find(" that ")
    if i < 0:
        return None
    start = i + len(" that ")
    end = len(sentence.rstrip(".!?"))
    return (start, end) if end > start else None


def produce(sentence: str, context: dict | None = None) -> list[dict]:
    mood = ((context or {}).get("source") or {}).get("mood")
    extra = {"mood": mood} if mood else {}
    claims = []
    clause = _clause(sentence)
    if "shout" in sentence:
        claim = {"relation": "shouts", "span": [0, len(sentence)],
                 "coordinates": {"tone": "loud", **extra},
                 "slots": {"clause.voice": "tone"}, "method": "fake-rule"}
        if clause:
            claim["links"] = [{"type": "temporal", "relation": "precedes",
                               "to_span": list(clause)}]
        claims.append(claim)
    if clause:
        claims.append({"relation": "nests", "span": list(clause),
                       "coordinates": {"tone": "calm", **extra}, "slots": {},
                       "method": "fake-rule"})
    return claims


def plane() -> dict:
    return {
        "plane": PLANE_ID,
        "language_version": VERSION,
        "nd_system": nd_system(),
        "binding": dict(BINDING),
        "produce": produce,
        "examples": [
            {"sentence": "Ann shouts.",
             "expected": produce("Ann shouts.")},
            {"sentence": "Bob says that it shouts loudly.",
             "expected": produce("Bob says that it shouts loudly.")},
        ],
    }
