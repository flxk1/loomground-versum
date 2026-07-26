"""versum/evidence.py — the store-backed evidence facade (K4, closes wire defect D4).

``StoreEvidenceProvider`` implements the ``EvidenceProvider`` port over one
by-domain KG store built by :mod:`versum.sync`: ``resolve(ref)`` returns the
cleaned source content a claim's span anchors into, and ``verify(ref)`` checks
source, item, span-bounds and content-digest consistency, fail-closed. It sits
behind the Solver's ``EvidenceProvider`` port (its ``grounded_text`` slices the
returned content with the ref's span) and behind any other consumer of stable
evidence references.

Contract notes (the WS13 corrected contract):

  * The provider is a **snapshot provider**: it binds at construction to the
    store's stamped ``graph_version`` and rejects every reference that does not
    carry exactly that token — empty, arbitrary, and stale ones included. A
    store that has moved on needs a new provider.
  * Content is the source file text passed through :func:`versum.io.extract.clean_text`
    — the same normalisation the extractor applied before computing spans, so
    offsets stay consistent. Content is read fresh on every resolution (no
    cache): tampering must be caught through the same provider instance.
  * Digests are ``sha256:<64-hex>`` over the UTF-8 cleaned content and are
    MANDATORY for ``verify`` — an absent or malformed digest fails, which is
    stricter than the Solver's inline provider (where a digest is optional).
    :meth:`content_digest` mints one for stamping refs at candidate-mint time.
  * PDF sources are not resolvable through this facade yet (their extraction
    text is layout-dependent); ``resolve`` raises and ``verify`` returns False —
    the safe direction. This is a known limitation; see the evidence ledger
    (``docs/reference/evidence.md``).
  * Batches are bounded by ``ports.MAX_EVIDENCE_BATCH``, consumed incrementally
    (an oversize or non-terminating iterable is rejected without being
    materialized), and index-aligned.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..io.extract import clean_text
from ..store.index import PDF_EXT
from ..ports import MAX_EVIDENCE_BATCH
from ..snapshot import require_graph_version
from ..sync import BY_DOMAIN, _read_rows


_DIGEST_FORM = re.compile(r"^sha256:[0-9a-f]{64}$")


class StoreEvidenceProvider:
    """Resolve/verify evidence refs against one minted snapshot of a by-domain store.

    ``libraries`` maps library id → library root path (the same association the
    sync config declares); ``sources.csv`` records only library-relative paths.
    Construction reads the store's stamped ``graph_version`` and fails when the
    store has never been synced.
    """

    def __init__(self, kg_root, libraries=None):
        self.kg_root = Path(kg_root)
        self.libraries = {str(k): Path(v) for k, v in (libraries or {}).items()}
        self.graph_version = require_graph_version(kg_root)
        self._sources = None   # canonical_urn -> {library, path}
        self._items = None     # (canonical_urn, item_id) present in claims.csv

    @classmethod
    def from_config(cls, config: dict) -> "StoreEvidenceProvider":
        """Build from a loaded Live Index config (see :func:`versum.sync.load_config`)."""
        return cls(config["kg_root"],
                   {lib["id"]: lib["root_path"]
                    for lib in config.get("libraries", [])})

    # ── scalar contract ──────────────────────────────────────────
    def resolve(self, ref) -> dict:
        """Return ``{source_id, item_id, content}`` for ``ref``.

        Raises ``ValueError`` for a ref outside this provider's snapshot and
        ``KeyError`` for an unknown source or claim item.
        """
        if ref.graph_version != self.graph_version:
            raise ValueError(
                "evidence ref does not carry this provider's snapshot "
                f"(got {ref.graph_version!r})")
        content = self._content_for(ref.source_id)
        if ref.item_id and (ref.source_id, ref.item_id) not in self._item_index():
            raise KeyError(f"unknown claim item: {(ref.source_id, ref.item_id)!r}")
        return {"source_id": ref.source_id, "item_id": ref.item_id,
                "content": content}

    def verify(self, ref) -> bool:
        """Source known, item known, span in bounds, digest present and matching — else False.

        The digest is mandatory and must be well-formed ``sha256:<64-hex>``: an
        absent or malformed digest fails verification outright (fail-closed) —
        a ref without one cannot make the tamper check meaningful. Producers
        stamp refs via :meth:`content_digest`.
        """
        try:
            payload = self.resolve(ref)
        except (KeyError, OSError, ValueError):
            return False
        content = payload["content"]
        if (ref.span_start is None) != (ref.span_end is None):
            return False
        if ref.span_start is not None:
            if not 0 <= ref.span_start < ref.span_end or ref.span_end > len(content):
                return False
        if not _DIGEST_FORM.fullmatch(str(ref.content_digest or "").lower()):
            return False
        return self._digest(content) == ref.content_digest.lower()

    # ── bounded-batch contract ───────────────────────────────────
    def resolve_batch(self, refs) -> list:
        out = []
        for ref in self._bounded(refs):
            try:
                out.append(self.resolve(ref))
            except (KeyError, OSError, ValueError):
                out.append(None)
        return out

    def verify_batch(self, refs) -> list:
        return [self.verify(ref) for ref in self._bounded(refs)]

    # ── digest minting for candidate producers ───────────────────
    def content_digest(self, source_id: str) -> str:
        """The ``sha256:<hex>`` digest of a source's cleaned content, for stamping refs."""
        return self._digest(self._content_for(source_id))

    # ── internals ────────────────────────────────────────────────
    @staticmethod
    def _bounded(refs):
        """Yield at most ``MAX_EVIDENCE_BATCH`` refs, consuming incrementally.

        Rejection happens at the first excess item, so an oversize — or
        non-terminating — iterable is never materialized.
        """
        for index, ref in enumerate(refs):
            if index >= MAX_EVIDENCE_BATCH:
                raise ValueError(
                    f"evidence batch exceeds {MAX_EVIDENCE_BATCH}")
            yield ref

    @staticmethod
    def _digest(content: str) -> str:
        return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _content_for(self, source_id: str) -> str:
        entry = self._source_index().get(source_id)
        if entry is None:
            raise KeyError(f"unknown evidence source: {source_id!r}")
        root = self.libraries.get(entry["library"])
        if root is None:
            raise KeyError(f"no root configured for library {entry['library']!r}")
        path = root / entry["path"]
        if path.suffix.lower() in PDF_EXT:
            raise ValueError(f"PDF sources are not resolvable yet: {entry['path']}")
        # Deliberately uncached: the same provider instance must see a
        # tampered source on the next resolution.
        return clean_text(path.read_text(encoding="utf-8", errors="replace"))

    def _source_index(self) -> dict:
        if self._sources is None:
            self._sources = {}
            for row in self._rows("sources.csv"):
                urn = (row.get("canonical_urn") or row.get("source_urn") or "").strip()
                if urn:
                    self._sources[urn] = {"library": row.get("library", ""),
                                          "path": row.get("path", "")}
        return self._sources

    def _item_index(self) -> set:
        if self._items is None:
            self._items = {
                ((row.get("canonical_urn") or "").strip(),
                 (row.get("item_id") or "").strip())
                for row in self._rows("claims.csv")
            }
        return self._items

    def _rows(self, filename: str):
        base = self.kg_root / BY_DOMAIN
        if not base.exists():
            return
        for table in sorted(base.glob(f"*/{filename}")):
            _cols, rows = _read_rows(table)
            yield from rows
