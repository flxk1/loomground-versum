"""inbox/year.py — Pass 2 year: resolve a publication year, never the filesystem time.

Product layer, OUTSIDE the versum engine. Fills the ``year`` field of an inbox sidecar from
the strongest available signal, in priority order:

  1. a **canonical identifier** the file carries (via an injected ``id_year`` resolver — the
     mapping from a scheme+id to a year is domain knowledge and is supplied, never baked in);
  2. **embedded document metadata** (e.g. a PDF ``CreationDate``) when it reads as a plausible
     publication year;
  3. a **year in the title or filename** (a four-digit year in a sane range);
  4. otherwise **undated** — a first-class outcome, not an error.

The filesystem modification time is NEVER consulted: a recently-touched file with old content
resolves to the old year (or undated), never to today. Deterministic; no network.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from versum.identity.core import pdf_meta

from .provenance import sidecar_path, SIDE

UNDATED = "undated"
_YEAR_RE = re.compile(r"(?<!\d)(1[5-9]\d{2}|20\d{2})(?!\d)")
# a PDF date is typically ``D:YYYYMMDD...`` or ``YYYY...``; pull the leading 4-digit year.
_PDFDATE_RE = re.compile(r"D?:?\s*(1[5-9]\d{2}|20\d{2})")

# floor keeps a stray page number or code from reading as a year; ceiling is resolved live.
_FLOOR = 1500


def _ceiling() -> int:
    return datetime.now(timezone.utc).year + 1


def _plausible(y: int) -> bool:
    return _FLOOR <= y <= _ceiling()


def year_from_meta(path) -> str | None:
    """A plausible publication year from embedded document metadata, else ``None``."""
    meta = pdf_meta(path)
    for key in ("CreationDate", "ModDate", "Date"):
        raw = str(meta.get(key) or "")
        m = _PDFDATE_RE.search(raw)
        if m and _plausible(int(m.group(1))):
            return m.group(1)
    return None


def year_from_text(*candidates: str) -> str | None:
    """The latest plausible four-digit year found in the given strings (title, filename), else None."""
    best = None
    for s in candidates:
        for m in _YEAR_RE.finditer(s or ""):
            y = int(m.group(1))
            if _plausible(y) and (best is None or y > best):
                best = y
    return str(best) if best is not None else None


def resolve_year(artifact_path, sidecar: dict, id_year=None) -> tuple[str, str]:
    """Return ``(year, method)`` for one artifact. ``method`` in
    {canonical-id, doc-metadata, title, filename, undated}. ``id_year`` is an optional
    ``(scheme, identifier) -> year|None`` callable that supplies canonical-id years.
    """
    p = Path(artifact_path)
    if id_year is not None:
        scheme = (sidecar.get("identity_method") or "").strip()
        ident = (sidecar.get("identifier") or "").strip()
        if scheme and ident:
            y = id_year(scheme, ident)
            if y and _plausible(int(y)):
                return str(int(y)), "canonical-id"

    y = year_from_meta(p)
    if y:
        return y, "doc-metadata"

    y = year_from_text(sidecar.get("title", ""))
    if y:
        return y, "title"
    y = year_from_text(p.name)
    if y:
        return y, "filename"

    return UNDATED, "undated"


def apply_year(inbox, id_year=None) -> dict:
    """Resolve and record ``year``/``year_method`` in every provenance sidecar. Idempotent."""
    inbox = Path(inbox)
    counts: dict[str, int] = {}
    outcomes = []
    for sc in sorted(inbox.glob("*" + SIDE)):
        try:
            d = json.loads(sc.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not (d.get("canonical_urn") or "").strip():
            continue
        name = d.get("source_file") or sc.name[:-len(SIDE)]
        year, method = resolve_year(inbox / name, d, id_year=id_year)
        if d.get("year") != year or d.get("year_method") != method:
            d["year"] = year
            d["year_method"] = method
            sc.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        counts[method] = counts.get(method, 0) + 1
        outcomes.append({"artifact": name, "year": year, "method": method})
    return {"counts": counts, "outcomes": outcomes}
