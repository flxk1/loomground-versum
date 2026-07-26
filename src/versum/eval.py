"""Evaluation harness — domain-general metrics for the concept layer (P7).

A scorer only. **No domain knowledge lives here** — no gold sets, no vocabulary. A gold
set is per-domain DATA the caller supplies; ``score`` takes it as a required argument.
Any specific corpus or subject area is only an example used to exercise the pipeline; it
is never a requirement baked into the engine.

- ``score(found, gold)`` — set-based precision / recall / f1 against a caller gold set.
- ``mint_curve(per_doc_sets)`` — convergence signal: new concepts contributed per doc.
- ``load_gold(path)`` — read a gold set (one slug per line) from a data file.
"""
from __future__ import annotations

from pathlib import Path


def score(found_slugs, gold) -> dict:
    """Set-based precision / recall / f1 of ``found_slugs`` against a ``gold`` set.

    ``gold`` is REQUIRED and caller-supplied — the scorer holds no domain default.
    Returns {precision, recall, f1, tp, fp, fn}.
    """
    found = set(found_slugs)
    gold = set(gold)
    tp = len(found & gold)
    fp = len(found - gold)
    fn = len(gold - found)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) else 0.0)
    return {"precision": precision, "recall": recall, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn}


def mint_curve(per_doc_concept_sets) -> list[int]:
    """Convergence signal: given an ORDERED list of per-document concept-id sets,
    return how many concepts each document adds that weren't seen in any earlier
    document. A converging pipeline's curve decays toward zero.
    """
    seen: set = set()
    curve: list[int] = []
    for s in per_doc_concept_sets:
        s = set(s)
        curve.append(len(s - seen))
        seen |= s
    return curve


def load_gold(path) -> frozenset:
    """Load a gold set from a data file: one concept slug per line; blank lines and
    lines starting with ``#`` are ignored. Gold sets are per-domain user data, not
    framework constants.
    """
    out = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line)
    return frozenset(out)
