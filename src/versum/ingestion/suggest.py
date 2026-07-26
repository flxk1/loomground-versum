"""inbox/suggest.py — rank placement suggestions from shared mental models.

Product layer, OUTSIDE the versum engine (no domain vocabulary in code). Given the concept
set a document grounds onto, rank the libraries/domains it most resembles and the individual
sources closest to it, by rarity-weighted (IDF) concept overlap. This produces a *suggestion*
for the review queue and the evidence behind it — it never files anything and never decides a
domain; a person (or an LLM acting for one) confirms.

The store it ranks against is the engine's by-domain concept table: each ``concepts.csv`` maps
``canonical_urn -> concept_id`` under a domain folder. A concept-id is a coordinate
(predicate + object), so it is comparable across domains — the same mental model recurring in
two folders is a real signal, not a coincidence of naming. No network.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Index:
    """An in-memory concept index over a by-domain store."""
    concepts: dict          # urn -> frozenset(concept_id)
    domain: dict            # urn -> domain (folder name)
    idf: dict               # concept_id -> inverse-document-frequency weight


def build_index(store_dir, by_domain="by-domain", exclude=("_archive", "unsorted")) -> Index:
    """Build an :class:`Index` from ``<store_dir>/<by_domain>/*/concepts.csv``."""
    concepts: dict[str, set] = defaultdict(set)
    domain: dict[str, str] = {}
    root = os.path.join(store_dir, by_domain)
    for f in glob.glob(os.path.join(root, "*", "concepts.csv")):
        dom = os.path.basename(os.path.dirname(f))
        if dom in exclude:
            continue
        with open(f, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                u, c = row.get("canonical_urn"), row.get("concept_id")
                if u and c:
                    concepts[u].add(c)
                    domain.setdefault(u, dom)
    frozen = {u: frozenset(cs) for u, cs in concepts.items()}
    n = len(frozen) or 1
    df: dict[str, int] = defaultdict(int)
    for cs in frozen.values():
        for c in cs:
            df[c] += 1
    idf = {c: math.log(n / k) for c, k in df.items()}
    return Index(concepts=frozen, domain=domain, idf=idf)


def _weight(concept_ids, idf) -> dict:
    return {c: idf.get(c, 0.0) for c in concept_ids}


def _score(qw: dict, sw: dict) -> float:
    """IDF-weighted cosine between two weighted concept sets."""
    if not qw or not sw:
        return 0.0
    inter = set(qw) & set(sw)
    if not inter:
        return 0.0
    dot = sum(qw[c] * sw[c] for c in inter)
    qn = math.sqrt(sum(v * v for v in qw.values()))
    sn = math.sqrt(sum(v * v for v in sw.values()))
    return dot / (qn * sn) if qn and sn else 0.0


def nearest_sources(query_concepts, index: Index, top_k: int = 5, exclude_urn=None) -> list[dict]:
    """The ``top_k`` sources closest to ``query_concepts`` by IDF-weighted overlap."""
    qw = _weight(set(query_concepts), index.idf)
    scored = []
    for u, cs in index.concepts.items():
        if u == exclude_urn:
            continue
        s = _score(qw, _weight(cs, index.idf))
        if s > 0:
            scored.append((s, u))
    scored.sort(reverse=True)
    return [{"urn": u, "domain": index.domain.get(u, ""), "score": round(s, 4)}
            for s, u in scored[:top_k]]


def rank_domains(query_concepts, index: Index, top_k: int = 5, exclude_urn=None) -> list[dict]:
    """Rank domains for ``query_concepts`` by their single closest member (nearest-neighbour
    semantics), returning the best score and the sources that carry it as evidence.
    """
    qw = _weight(set(query_concepts), index.idf)
    best: dict[str, tuple] = {}       # domain -> (score, urn)
    for u, cs in index.concepts.items():
        if u == exclude_urn:
            continue
        s = _score(qw, _weight(cs, index.idf))
        if s <= 0:
            continue
        dom = index.domain.get(u, "")
        if dom not in best or s > best[dom][0]:
            best[dom] = (s, u)
    ranked = sorted(best.items(), key=lambda kv: -kv[1][0])[:top_k]
    return [{"domain": d, "score": round(s, 4), "nearest_source": u} for d, (s, u) in ranked]


# ── effort policy: how much model power a placement call gets ────
# A routing HINT, never a filing gate — nothing is auto-filed on it; a person confirms every
# placement. The default is a cost-aware cascade, but it is fully user-configurable: a user with
# tokens to spend can send everything to the cloud model, a privacy-first user can pin it local,
# and either can override the cascade tuning. Defaults below are tunable, not sacred.
STRONG_DOMINANCE = 0.5     # cascade: top-1 leads top-2 by >= this fraction of top-1 → one domain
MIN_SIGNAL = 0.02          # cascade: below this the overlap is not real signal


@dataclass(frozen=True)
class Policy:
    """User effort preference. ``mode``:
      * ``cascade``       — cheapest sufficient tier by evidence shape (default).
      * ``cloud``         — the cloud model drafts every placement (tokens available; the mode
                            IS the cloud opt-in).
      * ``local``         — a local model drafts every placement; stays on the machine.
      * ``deterministic`` — no model; the deterministic suggestion goes straight to a person.
    In ``cascade`` mode, ``allow_cloud`` and ``local_available`` gate escalation.
    """
    mode: str = "cascade"
    allow_cloud: bool = False        # cascade: may escalate to cloud (privacy/cost opt-in)
    local_available: bool = True     # a local model is wired
    dominance: float = STRONG_DOMINANCE
    min_signal: float = MIN_SIGNAL


def load_policy(obj) -> Policy:
    """Build a :class:`Policy` from a dict (optionally under an ``effort`` key) or a JSON path.
    Missing keys take the defaults; ``None``/missing input yields the default cascade policy.
    """
    if obj is None:
        return Policy()
    if isinstance(obj, (str, bytes)):
        import os
        if not os.path.exists(obj):
            return Policy()
        obj = json.loads(open(obj, encoding="utf-8").read())
    eff = obj.get("effort", obj) if isinstance(obj, dict) else {}
    f = {k: eff[k] for k in ("mode", "allow_cloud", "local_available", "dominance", "min_signal")
         if k in eff}
    return Policy(**f)


def _cap(tier: str, policy: Policy) -> str:
    """Downgrade a desired tier that policy cannot satisfy — never silently escalate."""
    if tier == "cloud-llm" and not policy.allow_cloud:
        return "local-llm" if policy.local_available else "review"
    if tier == "local-llm" and not policy.local_available:
        return "cloud-llm" if policy.allow_cloud else "review"
    return tier


def recommend_tier(ranked_domains, policy: Policy = None) -> dict:
    """Which tier drafts this placement, under the user's policy. Tiers: ``regex`` (deterministic
    suggestion → person), ``local-llm``, ``cloud-llm``, or ``review`` (no model available/allowed —
    a person decides). A hint only; a person confirms every placement.
    """
    policy = policy or Policy()
    if policy.mode == "cloud":
        return {"tier": "cloud-llm", "reason": "policy: cloud model drafts every placement"}
    if policy.mode == "local":
        t = "local-llm" if policy.local_available else "review"
        return {"tier": t, "reason": "policy: local model drafts every placement"
                if t == "local-llm" else "policy is local-only but no local model is wired — review"}
    if policy.mode == "deterministic":
        return {"tier": "regex", "reason": "policy: deterministic suggestion only, no model call"}

    # cascade (default): evidence shape picks the desired tier, then policy caps it.
    if not ranked_domains or ranked_domains[0]["score"] < policy.min_signal:
        desired, why = "cloud-llm", "no clear mental-model neighbour (novel or noisy)"
    else:
        top1 = ranked_domains[0]["score"]
        top2 = ranked_domains[1]["score"] if len(ranked_domains) > 1 else 0.0
        if (top1 - top2) >= policy.dominance * top1:
            desired, why = "regex", "one dominant neighbour domain — deterministic suffices"
        else:
            desired, why = "local-llm", "several close neighbour domains — a model should read it"
    capped = _cap(desired, policy)
    reason = why if capped == desired else f"{why}; capped to {capped} by policy"
    return {"tier": capped, "reason": reason}


def suggest(query_concepts, index: Index, top_k: int = 5, exclude_urn=None, policy: Policy = None) -> dict:
    """Both views for one query: ranked domains + nearest sources, plus the recommended effort
    tier under the given policy. A suggestion, not a filing."""
    domains = rank_domains(query_concepts, index, top_k, exclude_urn)
    return {"domains": domains,
            "sources": nearest_sources(query_concepts, index, top_k, exclude_urn),
            "n_query_concepts": len(set(query_concepts)),
            "recommended_tier": recommend_tier(domains, policy)}
