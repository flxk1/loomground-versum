"""versum/consume.py — consume the KG's 19-column source registry (ADR-URN, option B).

Phase 0.5 gave capture and index ONE shared deterministic identity resolver. Phase 1 layers
option B on top: before minting, the indexer/guard *reads the KG registry* — a 19-column
``source_registry.csv`` the upstream KG already produced — and, for a file already in it,
**reuses** that row's ``canonical_urn`` (and ``version_urn``) as the source URN rather than
minting a parallel one. Only when neither the registry nor an inbox sidecar settles a file's
identity does it fall back to ``identity.deterministic_identity`` under the library namespace.

Matching is deterministic and content-free:
  * a registry row is matched **by ``original_path``** (the relpath) primarily, and by bare
    ``filename`` as a fallback;
  * an inbox **sidecar** (``*.metadata.json``) is matched by its **stub name** and carries
    the authoritative ``canonical_urn``.

This module reads CSV/JSON already on disk. It writes nothing, fetches nothing, and names no
domain vocabulary — the 19 columns are structural, not domain-specific.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

# The authoritative 19-column KG registry schema. We read these columns; we never
# redefine or shadow them (the .versum store only *references* the canonical_urn).
REGISTRY_COLUMNS = [
    "source_id", "canonical_urn", "version_urn", "original_path", "filename",
    "extension", "detected_year", "title_guess", "author_or_institution_guess",
    "document_type", "primary_topic", "topics", "jurisdiction", "citation",
    "description", "inference_level", "duplicate_key", "duplicate_group_size",
    "size_bytes",
]

# the subset the Versum carries forward as provenance context for a reused source
_CARRY = ("canonical_urn", "version_urn", "primary_topic", "topics",
          "jurisdiction", "detected_year")


def _norm(relpath: str) -> str:
    """Normalise a path key to forward-slash, no leading ``./``."""
    return Path(str(relpath)).as_posix().lstrip("./") if relpath else ""


class Registry:
    """An in-memory index of a KG ``source_registry.csv``, keyed by original_path & filename.

    ``reuse_urn`` returns the row's ``canonical_urn`` for a file already registered, else
    ``None`` (the caller then falls back to deterministic minting).
    """

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self._by_path: dict[str, dict] = {}
        self._by_name: dict[str, dict] = {}
        self._ambiguous_names: set[str] = set()
        for r in rows:
            op = _norm(r.get("original_path", ""))
            if op:
                self._by_path.setdefault(op, r)
            fn = (r.get("filename") or "").strip()
            if fn:
                prev = self._by_name.get(fn)
                if prev is None:
                    self._by_name[fn] = r
                elif (prev.get("canonical_urn") or "") != (r.get("canonical_urn") or ""):
                    # same filename, DIFFERENT canonical_urn → ambiguous. Refuse to guess:
                    # a filename-only match must never mis-key a document. relpath (unique)
                    # still resolves it; the caller falls back to deterministic minting.
                    self._ambiguous_names.add(fn)

    def __len__(self) -> int:
        return len(self.rows)

    def row_for(self, relpath: str | None = None, filename: str | None = None) -> dict | None:
        """Return the registry row for a file — by relpath (primary), then by filename."""
        if relpath:
            hit = self._by_path.get(_norm(relpath))
            if hit:
                return hit
        name = filename or (Path(relpath).name if relpath else None)
        if name and name not in self._ambiguous_names:
            return self._by_name.get(name)
        return None

    def reuse_urn(self, relpath: str | None = None, filename: str | None = None) -> str | None:
        """The ``canonical_urn`` to REUSE for this file, or ``None`` if not registered."""
        row = self.row_for(relpath, filename)
        if not row:
            return None
        return (row.get("canonical_urn") or "").strip() or None

    def provenance_for(self, relpath: str | None = None,
                       filename: str | None = None) -> dict | None:
        """The carried provenance context (``_CARRY`` subset) for a registered file, else None."""
        row = self.row_for(relpath, filename)
        if not row:
            return None
        return {k: (row.get(k) or "").strip() for k in _CARRY}


def read_registry(csv_path) -> Registry:
    """Read a 19-column KG ``source_registry.csv`` into a :class:`Registry`."""
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return Registry(rows)


# ── inbox sidecars ────────────────────────────────────────────────
def read_sidecars(inbox_dir) -> dict[str, dict]:
    """Map ``stub name -> {canonical_urn, title, ...}`` for every inbox ``*.metadata.json``.

    The stub name is the sidecar filename with the ``.metadata.json`` suffix stripped
    (e.g. ``foo.md.metadata.json`` -> ``foo.md``). Sidecars with no ``canonical_urn`` are
    skipped. This is the inbox counterpart to a registry row: identity settled by sidecar.
    """
    out: dict[str, dict] = {}
    suffix = ".metadata.json"
    for p in sorted(Path(inbox_dir).rglob("*" + suffix)):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        urn = (d.get("canonical_urn") or "").strip()
        if not urn:
            continue
        stub = p.name[:-len(suffix)]
        out[stub] = {"canonical_urn": urn, "title": d.get("title", ""),
                     "sidecar": p.name, "stub": stub}
    return out


def sidecar_urn_for(stub_name: str, sidecars: dict[str, dict]) -> str | None:
    """The ``canonical_urn`` a sidecar settles for this stub name, or ``None``."""
    hit = sidecars.get(stub_name)
    return hit["canonical_urn"] if hit else None


# ── the PDF-without-registry gap ─────────────────────────────────
def missing_from_registry(relpaths, registry: Registry) -> list[str]:
    """Return the relpaths that have NO registry row — the PDF-without-registry gap.

    These are library files the KG registry does not cover; the caller queues them for
    mint+register or excludes-with-count, so they are handled, never silently dropped.
    Order is preserved and de-duplicated.
    """
    missing: list[str] = []
    seen: set[str] = set()
    for rp in relpaths:
        key = _norm(rp)
        if key in seen:
            continue
        seen.add(key)
        if registry.row_for(relpath=rp) is None:
            missing.append(rp)
    return missing
