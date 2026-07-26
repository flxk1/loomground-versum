"""versum/urn.py — the ONE shared source-URN derivation (ADR-URN, option A).

Both the write guard (``write.resolve_identity``'s path-slug fallback) and the indexer
(``index._urn_for``) must mint the SAME ``urn:<namespace>:source:<slug>`` for a file when
no canonical id / KG sidecar settles its identity. They do that by importing the SAME
symbol from here.

The slug is derived from the file **stem only** — no extension, no subdirectory — with a
single truncation rule, so capture and index agree byte-for-byte on the URN.

Domain-neutral: ``namespace`` is supplied by the caller (from the active profile); nothing
here hardcodes a domain.
"""
from __future__ import annotations

import re

_SLUG_MAX = 80


def source_slug(stem: str) -> str:
    """Lowercase → collapse non-alphanumerics to '-' → strip → truncate. Stem only."""
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")[:_SLUG_MAX]


def source_urn_for(stem: str, namespace: str) -> str:
    """The stable source URN for a file with this stem under this namespace.

    ``stem`` MUST be the bare filename stem (``Path.stem``) — no extension, no directory.
    """
    return f"urn:{namespace}:source:{source_slug(stem)}"
