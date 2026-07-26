"""versum/run.py — Phase 2 slice runner + derived pdf_status (loops 3 & 4).

Two derived signals the 19-column registry does NOT record, computed here from disk:

* :func:`pdf_status` — is a source's *bytes* present? ``'processable'`` iff a file exists
  at ``root_path + relpath`` for the library, else ``'citation-only'``. Nothing in the
  registry states this; it is DERIVED from the filesystem (loop 3).

* :func:`run_slice` — index a folder against a consume registry and emit a per-source
  *ledger* plus a *summary*. Registry-backed files REUSE the KG ``canonical_urn``
  (provenance ``kg-registry``); files with no registry row MINT one (provenance
  ``minted``); registry rows in the slice whose bytes are absent are recorded
  ``citation-only`` / skipped. ``reuse_rate`` / ``mint_rate`` (over the processed sources)
  are the convergence SIGNAL for one run — reported, not a claim that convergence holds.

Pure aggregate over what identity resolution + the filesystem already decided; names no
domain vocabulary, mints no URNs of its own, no network.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .store.index import index_folder
from .libraries import LibrariesRegistry


def pdf_status(relpath, libraries_registry: LibrariesRegistry, library: str) -> str:
    """``'processable'`` iff a file exists at ``root_path + relpath`` for ``library``.

    DERIVED — the registry records no such column. Resolve the library's root and test the
    filesystem; a not-yet-arrived (or citation-only) source resolves to ``'citation-only'``.
    No network.
    """
    try:
        resolved = libraries_registry.resolve(library, relpath)
    except Exception:
        return "citation-only"
    return "processable" if resolved.is_file() else "citation-only"


def _matches_domain(row: dict, substring: str) -> bool:
    """True iff ``substring`` (case-insensitive) appears in the row's path/topic fields.

    Empty substring matches every row. The match is structural (path + topic columns),
    naming no domain value itself.
    """
    if not substring:
        return True
    hay = " ".join(
        str(row.get(k, "")) for k in ("original_path", "primary_topic", "topics"))
    return substring.lower() in hay.lower()


def run_slice(registry, library: str, root, domain_substring: str,
              folder_for_index, profile_id: str = "generic") -> dict:
    """Index ``folder_for_index`` against ``registry`` and return ``{ledger, summary}``.

    ``registry`` is a :class:`versum.io.consume.Registry`; ``root`` is the library's root_path
    (used to derive :func:`pdf_status`); ``domain_substring`` selects which registry rows
    form the slice (matched against path/topic columns). The folder is indexed with the
    registry as the ``consume`` source, so a file already registered reuses its
    ``canonical_urn`` and a file that is not mints one.

    The ledger has one row per source: indexed files (``processed`` / ``processable``) with
    their claim count and provenance, plus registry rows in the slice whose bytes are absent
    (``skipped`` / ``citation-only``). The summary reports the counts and the
    ``reuse_rate`` / ``mint_rate`` over the processed sources.
    """
    libs = LibrariesRegistry({library: {"root_path": str(root), "urn_namespace": library}})

    # Index the folder. Registry-backed files reuse canonical_urn (kg-registry); the rest
    # mint under the library namespace. use_kg_provenance is off so provenance is purely
    # kg-registry|minted — the convergence signal is unambiguous.
    manifest = index_folder(folder_for_index, profile_id=profile_id, consume=registry,
                            library=library, namespace=library, use_kg_provenance=False)
    out = Path(manifest["out"])

    with open(out / "sources.csv", newline="", encoding="utf-8") as fh:
        indexed = list(csv.DictReader(fh))

    ledger: list[dict] = []
    seen_relpaths: set[str] = set()
    for s in indexed:
        rp = s.get("path", "")
        seen_relpaths.add(rp)
        ledger.append({
            "canonical_urn": s.get("canonical_urn", ""),
            "source_urn": s.get("source_urn", ""),
            "relpath": rp,
            "pdf_status": "processable",
            "status": "processed",
            "n_claims": int(s.get("n_items") or 0),
            "provenance": s.get("provenance", ""),
        })

    # Registry rows in the slice whose bytes are absent → citation-only (skipped).
    seen_citation: set[str] = set()
    for r in registry.rows:
        if not _matches_domain(r, domain_substring):
            continue
        rel = (r.get("original_path") or "").strip()
        if not rel or rel in seen_relpaths or rel in seen_citation:
            continue
        if pdf_status(rel, libs, library) == "processable":
            continue  # bytes present ⇒ already covered by the indexed set
        seen_citation.add(rel)
        ledger.append({
            "canonical_urn": (r.get("canonical_urn") or "").strip(),
            "source_urn": "",
            "relpath": rel,
            "pdf_status": "citation-only",
            "status": "skipped",
            "n_claims": 0,
            "provenance": "citation-only",
        })

    n_processable = sum(1 for e in ledger if e["pdf_status"] == "processable")
    n_citation_only = sum(1 for e in ledger if e["pdf_status"] == "citation-only")
    n_reuse = sum(1 for e in ledger if e["provenance"] == "kg-registry")
    n_mint = sum(1 for e in ledger if e["provenance"] == "minted")
    total = n_processable  # processed sources = the convergence denominator
    summary = {
        "library": library,
        "domain_substring": domain_substring,
        "n_sources": len(ledger),
        "n_processable": n_processable,
        "n_citation_only": n_citation_only,
        "n_reuse": n_reuse,
        "n_mint": n_mint,
        "reuse_rate": (n_reuse / total) if total else 0.0,
        "mint_rate": (n_mint / total) if total else 0.0,
    }
    return {"ledger": ledger, "summary": summary}
