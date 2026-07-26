"""versum/kg.py — consume an existing KG's provenance instead of minting a parallel one.

An upstream KG may already own provenance: a capture / deep-research workflow writes a
stub `*.md` plus a sidecar `*.md.metadata.json` carrying the authoritative `canonical_urn`.
When the Versum indexes a folder that already has such provenance, it must **reuse the KG's
`canonical_urn`** as the claim's `source_urn` — never mint its own parallel URN. That is
the join between the KG's provenance floor and the Versum's additive 5D+nD layer: both key
on the same URN.

This module reads the sidecars and matches a source file to its KG URN. It writes nothing
and fetches nothing.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

# a structured identifier token (digits+letters+digits), matched in both filename and URN
_IDTOK = re.compile(r"[0-9]{5}[a-z]{1,2}[0-9]{3,4}", re.IGNORECASE)


def load_sidecars(folder) -> list[dict]:
    """Read every KG capture sidecar (*.metadata.json) under folder that has a canonical_urn."""
    out = []
    for p in Path(folder).rglob("*.metadata.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        urn = (d.get("canonical_urn") or "").strip()
        if urn:
            out.append({
                "canonical_urn": urn, "title": d.get("title", ""),
                "pdf_status": d.get("pdf_status", ""), "verification": d.get("verification", ""),
                "authority_tier": d.get("authority_tier", ""),
                "topic": d.get("topic"), "subtopic": d.get("subtopic"),
                "jurisdiction": d.get("jurisdiction"), "year": d.get("year"),
                "sidecar": p.name, "stub": p.name[:-len(".metadata.json")],
            })
    return out


def is_kg_stub(path, folder) -> bool:
    """True if path is a KG citation stub (.md that has a paired .metadata.json)."""
    p = Path(path)
    return p.suffix.lower() == ".md" and p.with_name(p.name + ".metadata.json").exists()


def provenance_urn_for(path, sidecars) -> str | None:
    """Return the KG canonical_urn to REUSE for this file, or None if the KG has no
    provenance for it. Deterministic match: a shared structured identifier token present
    in both the filename and a sidecar's canonical_urn; else a title-slug overlap.
    """
    name = urllib.parse.unquote(Path(path).name).lower()
    toks = {m.group(0).lower() for m in _IDTOK.finditer(name)}
    for s in sidecars:
        urn = s["canonical_urn"].lower()
        if toks and any(t in urn for t in toks):
            return s["canonical_urn"]
    # title-slug fallback: sidecar title tokens appearing in the filename
    for s in sidecars:
        twords = [w for w in re.split(r"[^a-z0-9]+", (s.get("title") or "").lower()) if len(w) > 4]
        if twords and sum(w in name for w in twords) >= max(2, len(twords) // 3):
            return s["canonical_urn"]
    return None
