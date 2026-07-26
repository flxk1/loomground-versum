"""versum/identity.py — the ONE shared deterministic identity resolution (ADR-URN, option A).

Both the write guard (capture) and the indexer must assign a file the SAME source URN, so
the provenance row and the claim rows join. Identity is resolved in rungs, most-authoritative
first:

  0. a profile identifier scheme (``profile.source_identifiers`` — the profile names them),
  1. a PDF ``Title`` slug,
  2. a **content hash** of the file's bytes (``urn:<ns>:sha256:<digest>``) when the binary
     is on disk — content-addressed, so it is stable under rename and distinct for distinct
     bytes,
  3. a filename slug (``versum.identity.urn.source_urn_for``) — the degraded last resort, reached only
     for a source with no canonical id, no title, and **no local bytes to hash** (a
     citation-only record, or a path that does not exist yet).

Capture and index both call ``deterministic_identity`` and therefore agree byte-for-byte at
whichever rung settles the identity.

ADR-URN-2 (identity spine hardening): rung 2 was added to close a fork/collision in the old
filename fallback — a rename minted a new URN, and two different files sharing a filename
collided onto one URN. Content-addressing fixes both when bytes exist. Rung 3 survives only
for the no-content case, where there is genuinely nothing to hash. Rungs 0–1 are unchanged,
so no existing canonical- or title-keyed URN moves.

Domain-neutral: every identifier scheme comes from the active profile; the core names none.
No network.
"""
from __future__ import annotations

import hashlib
import urllib.parse
from pathlib import Path

from .urn import source_slug, source_urn_for

PDF_EXT = {".pdf"}

# The two degraded fallback rungs (content-hash, then filename). ``write.resolve_identity``
# escalates through the resolver ladder only when identity landed on one of these — the
# ambiguous cases; a canonical scheme or a title never escalates.
FALLBACK_METHODS = frozenset({"content-sha256", "path-slug"})


def content_sha256(path) -> str | None:
    """Hex SHA-256 of the file's bytes, or ``None`` when the file cannot be read.

    ``None`` is the signal that there are no local bytes to content-address (a citation-only
    source, or a path that does not exist) — the caller then falls to the filename rung.
    Streamed in chunks so a large binary does not load into memory. No network.
    """
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, ValueError):
        return None


def pdf_meta(path) -> dict:
    """Best-effort PDF metadata; ``{}`` for non-PDF or on any error. No network."""
    p = Path(path)
    if p.suffix.lower() not in PDF_EXT:
        return {}
    try:
        import pdfplumber
        with pdfplumber.open(str(p)) as pdf:
            return dict(pdf.metadata or {})
    except Exception:
        return {}


def deterministic_identity(path, profile, meta=None, namespace=None):
    """Return ``(urn, identifier, method, title, verification)`` for a file — rung 0 only.

    Resolution order: profile identifier schemes → PDF title → shared path-slug. This is the
    identity capture writes AND the identity the indexer keys its claims on, so both join —
    for canonical-id files and for plain files alike.

    ``namespace`` (loop 8) overrides the profile's baked namespace when supplied — sourced
    from the library's ``urn_namespace`` — so the SAME file under two libraries with
    different namespaces yields two distinct URNs. When ``None`` the profile namespace is
    used (unchanged behaviour).
    """
    p = Path(path)
    ns = namespace or profile.namespace
    if meta is None:
        meta = pdf_meta(p)
    name = urllib.parse.unquote(p.name)
    hay = f"{name}\n{meta.get('Title', '')}\n{meta.get('doi', '') or meta.get('DOI', '')}"
    title = (meta.get("Title") or p.stem).strip()

    # rung 0 — try each identifier scheme the profile recognises, in its declared order.
    for scheme, pattern in profile.source_identifiers:
        m = pattern.search(hay)
        if m:
            ident_id = m.group(1).lower().rstrip(".")
            return (f"urn:{ns}:{scheme}:{ident_id}", ident_id, scheme, title, "metadata")
    if meta.get("Title"):
        s = source_slug(meta["Title"])
        return (f"urn:{ns}:source:{s}", s, "pdf-title", title, "metadata")
    # rung 2 — content hash of the on-disk bytes. Rename-stable and collision-free for
    # distinct bytes; both sides derive it identically from the same file.
    digest = content_sha256(p)
    if digest is not None:
        return (f"urn:{ns}:sha256:{digest}", digest, "content-sha256", title, "content")
    # rung 3 — no local bytes to hash (citation-only, or a path that does not exist): the
    # degraded filename-slug last resort. NOT rename-stable — reached only when nothing
    # stronger is available.
    return (source_urn_for(p.stem, ns), source_slug(p.stem), "path-slug", title, "filename")
