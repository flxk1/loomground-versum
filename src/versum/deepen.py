"""versum/deepen.py — LLM deepening at the index step (ADR-005).

Deterministic-first, model-as-escalation. The deterministic coordinate layer models claims
at the surface and leaves ~80% unclustered; a local LLM can deepen exactly those. This is the
DETERMINISTIC HARNESS around that escalation:

  * ``escalation_candidates`` — deterministically pick and BOUND which items get a (costly) LLM
    call: unclustered residue first, then claims in dense units, under a call budget. No model
    is involved in choosing.
  * ``Deepener`` — the injected adapter contract; the real one runs device-side (Qwen/Phi via
    Ollama). ``NullDeepener`` (default) does nothing; ``EchoDeepener`` is a test stub.
  * ``deepen`` — run the adapter over the candidates, validate the shape, and return additive
    deepenings (also writable to ``deepenings.jsonl`` keyed on canonical_urn + item_id). The
    deterministic canon is never mutated.

Domain-neutral: names no domain value; deterministic given a deterministic adapter.
"""
from __future__ import annotations

import json
from pathlib import Path

# the structured shape a Deepener must return (validated; extra keys ignored)
DEEPENING_KEYS = ("relations", "sub_claims", "mental_model")


class Deepener:
    """Interface for an LLM deepener. Implemented device-side (Ollama Qwen/Phi); never called
    from core. ``deepen(text, context) -> dict`` with keys relations / sub_claims /
    mental_model (a richer structure than the deterministic coordinate)."""
    def deepen(self, text: str, context: dict) -> dict:  # pragma: no cover - interface
        raise NotImplementedError


class NullDeepener(Deepener):
    """Default: no deepening (engine runs model-free)."""
    def deepen(self, text, context):
        return {}


class EchoDeepener(Deepener):
    """Deterministic test stub — echoes a trivial, well-shaped structure. NOT a real model."""
    def deepen(self, text, context):
        return {"relations": [], "sub_claims": [t.strip() for t in text.split(";") if t.strip()],
                "mental_model": {"label": (text or "").strip()[:60]}}


def _valid(d: dict) -> dict:
    """Coerce an adapter result to the deepening shape; drop anything malformed."""
    if not isinstance(d, dict):
        return {}
    out = {}
    rel = d.get("relations")
    out["relations"] = rel if isinstance(rel, list) else []
    sub = d.get("sub_claims")
    out["sub_claims"] = [str(s) for s in sub] if isinstance(sub, list) else []
    mm = d.get("mental_model")
    out["mental_model"] = mm if isinstance(mm, dict) else {}
    return out


def escalation_candidates(claims, canon: dict | None = None, budget: int = 100,
                          policy: str = "residue-first") -> list[dict]:
    """Deterministically select ≤ ``budget`` claims to deepen.

    ``policy``:
      * ``residue-first`` (default) — claims the deterministic pass could NOT model come first
        (item_ids absent from any concept in ``canon``), then the rest; ties by item_id for
        determinism.
      * ``dense-first`` — claims in the largest units first (more context to deepen), then rest.

    Selection uses no model and is stable. ``canon`` is a ``build_canon`` result (its ``edges``
    tell which claims were clustered); ``None`` treats every claim as residue.
    """
    clustered: set = set()
    if canon:
        for e in canon.get("edges", []):
            sid = e.get("src_id")
            if sid:
                clustered.add(sid)

    def iid(c):
        return (c.get("item_id") or "").strip()

    if policy == "dense-first":
        unit_size: dict = {}
        for c in claims:
            key = (c.get("source_urn") or c.get("canonical_urn"), c.get("unit_id"))
            unit_size[key] = unit_size.get(key, 0) + 1
        ranked = sorted(claims, key=lambda c: (
            -unit_size.get((c.get("source_urn") or c.get("canonical_urn"), c.get("unit_id")), 0),
            iid(c)))
    else:  # residue-first
        ranked = sorted(claims, key=lambda c: (iid(c) in clustered, iid(c)))

    return ranked[:max(0, budget)]


def deepen(claims, deepener: Deepener | None = None, canon: dict | None = None,
           budget: int = 100, policy: str = "residue-first", out_path=None) -> list[dict]:
    """Deepen the selected candidates with the injected ``deepener`` (default ``NullDeepener``).

    Returns a list of additive deepening records ``{canonical_urn, item_id, deepening}`` (empty
    deepenings dropped). If ``out_path`` is given, also appends them as JSONL. The deterministic
    canon/claims are never modified.
    """
    dp = deepener or NullDeepener()
    cands = escalation_candidates(claims, canon=canon, budget=budget, policy=policy)
    ctx_of = {(c.get("item_id") or "").strip(): c for c in claims}
    records = []
    for c in cands:
        item_id = (c.get("item_id") or "").strip()
        ctx = {"predicate": c.get("predicate", ""), "domain": c.get("domain", ""),
               "unit_id": c.get("unit_id", "")}
        result = _valid(dp.deepen(c.get("text", ""), ctx))
        if not (result.get("relations") or result.get("sub_claims") or result.get("mental_model")):
            continue
        records.append({
            "canonical_urn": (c.get("canonical_urn") or c.get("source_urn") or "").strip(),
            "item_id": item_id, "deepening": result})
    records.sort(key=lambda r: (r["canonical_urn"], r["item_id"]))
    if out_path is not None:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return records


def promotion_plan(records, verifier) -> dict:
    """Verify additive deepenings before any host-specific promotion.

    ``verifier(record)`` is injected and must positively establish grounding/schema policy.
    The core supplies no permissive default: without a verifier nothing can be promoted.
    """
    if verifier is None:
        raise ValueError("deepening promotion requires an explicit verifier")
    accepted, rejected = [], []
    for record in records:
        reason = _promotion_shape_error(record)
        if reason is None:
            try:
                verified = bool(verifier(record))
            except Exception as exc:
                verified = False
                reason = f"verifier-error:{type(exc).__name__}"
            if not verified and reason is None:
                reason = "verification-failed"
        if reason is None:
            accepted.append(record)
        else:
            rejected.append({"canonical_urn": record.get("canonical_urn", ""),
                             "item_id": record.get("item_id", ""), "reason": reason})
    return {"accepted": accepted, "rejected": rejected,
            "n_accepted": len(accepted), "n_rejected": len(rejected)}


def promote(records, verifier, sink) -> dict:
    """Send only verified deepenings to an injected retention sink."""
    if sink is None:
        raise ValueError("deepening promotion requires an explicit retention sink")
    plan = promotion_plan(records, verifier)
    for record in plan["accepted"]:
        sink(record)
    return plan


def _promotion_shape_error(record) -> str | None:
    if not isinstance(record, dict):
        return "record-not-object"
    if not (record.get("canonical_urn") or "").strip():
        return "missing-source-identity"
    if not (record.get("item_id") or "").strip():
        return "missing-item-identity"
    deepening = record.get("deepening")
    if not isinstance(deepening, dict):
        return "missing-deepening"
    if set(DEEPENING_KEYS) - set(deepening):
        return "incomplete-deepening-schema"
    return None
