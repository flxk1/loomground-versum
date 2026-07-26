"""Loomground Versum — drop-in folder indexer.

Point it at ANY folder of files and it builds a knowledge-graph index *inside* that
folder, under a ``.versum/`` directory:

    <folder>/.versum/claims.csv          candidate claims (span-anchored, axis-stamped)
    <folder>/.versum/sources.csv         one row per indexed file (path -> source URN)
    <folder>/.versum/fingerprints.json   per-source 5D+nD fingerprint
    <folder>/.versum/concepts.csv        concept registry (empty until curation)
    <folder>/.versum/semantic_edges.csv  grounds/rhymes/part_of edges (empty until curation)
    <folder>/.versum/index.json          run manifest (profile, counts, skipped files)

Domain-agnostic: all vocabulary comes from the chosen ``Profile`` and the engine
privileges no domain. No external repo dependency, no network. Supported file types:
PDF (pdfplumber) and plain text / Markdown; anything else is recorded as skipped, never
silently dropped.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

from ..io import extract as ex
from ..identity import fingerprint as fp
from . import graph as g
from . import kg
from .. import profiles as _profiles  # noqa: F401 — registers built-in profiles
from ..identity.core import deterministic_identity
from ..profile import get_profile

PDF_EXT = {".pdf"}
TEXT_EXT = {".txt", ".md", ".markdown", ".text"}
SUPPORTED = PDF_EXT | TEXT_EXT

# sources.csv REFERENCES the KG registry via ``library`` + ``canonical_urn`` (Phase 1,
# reschema): it never shadows the 19-column KG registry, only links back to it.
SOURCE_COLUMNS = ["source_urn", "path", "n_items", "unit_type", "profile", "provenance",
                  "library", "canonical_urn"]
DEFINITION_COLUMNS = ["source_urn", "term", "term_slug", "span_start", "span_end"]


def _urn_for(path, profile, namespace=None) -> str:
    """The source URN for a file, via the ONE shared deterministic resolver.

    Delegates to ``identity.deterministic_identity`` — the *same* function the write guard
    uses — so a file's claim/source URN is byte-identical to the URN capture wrote, for
    canonical-id files (resolved by a profile identifier scheme) as well as plain ones
    (ADR-URN, option A). ``namespace`` (loop 8) overrides the profile namespace when the
    file belongs to a library with its own ``urn_namespace``.
    """
    return deterministic_identity(path, profile, namespace=namespace)[0]


def _extract_file(path: Path, urn: str, profile) -> dict:
    """Return an extractor-shaped result dict for a PDF or text file."""
    ext = path.suffix.lower()
    if ext in PDF_EXT:
        return ex.extract(str(path), urn, profile)
    text = ex.clean_text(path.read_text(encoding="utf-8", errors="replace"))
    units = ex.segment_units(text)
    items = [it for u in units for it in ex.candidate_items(u, urn, profile)]
    return {
        "source_urn": urn, "pdf": path.name, "n_chars": len(text),
        "n_units": len(units), "unit_type": units[0]["unit_type"] if units else None,
        "n_items": len(items), "profile": profile.id, "text": text,
        "units": units, "items": items,
    }


def _json_safe(obj):
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def _write_csv(path: Path, rows, columns) -> None:
    import csv
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _write_sources(path: Path, rows) -> None:
    _write_csv(path, rows, SOURCE_COLUMNS)


def index_folder(folder, profile_id: str = "generic", out=None,
                 use_kg_provenance: bool = True, namespace=None,
                 consume=None, library=None, nd_system_paths=None) -> dict:
    """Index every supported file under ``folder``; write the ``.versum/`` index.

    Existing ``concepts.csv`` / ``semantic_edges.csv`` are preserved (curation output is
    never clobbered); claims / sources / fingerprints are regenerated deterministically.

    When ``use_kg_provenance`` (default) and the folder already carries KG capture
    sidecars (``*.md.metadata.json`` with a ``canonical_urn``), a source's claims are
    keyed on the KG's own ``canonical_urn`` — the Versum reuses provenance instead of
    minting a parallel URN — and KG citation stubs (a ``.md`` with a paired sidecar) are
    skipped as sources. Returns a run manifest dict.

    Phase 1 (ADR-URN option B + loop 8):
      * ``consume`` — an optional :class:`versum.io.consume.Registry`. For a file whose relpath
        (or filename) matches a registry row, that row's ``canonical_urn`` is REUSED as the
        source URN instead of minting one.
      * ``namespace`` — an optional URN-namespace override (from a library's ``urn_namespace``)
        used when a file's identity must be minted; the same file under two libraries with
        different namespaces then gets two distinct URNs.
      * ``library`` — an optional library id recorded on each source row as provenance
        linkage back to the KG registry (never a copy of the 19-column registry).
    """
    profile = get_profile(profile_id)
    folder = Path(folder).resolve()
    out = Path(out).resolve() if out else folder / ".versum"
    out.mkdir(parents=True, exist_ok=True)

    from ..nd import NDRegistry
    nd_registry = NDRegistry(include_core=True).load(nd_system_paths or [])
    nd_dir = out / "nd"
    nd_dir.mkdir(parents=True, exist_ok=True)
    (nd_dir / "systems.json").write_text(
        json.dumps(nd_registry.manifest(), ensure_ascii=False, indent=2,
                   sort_keys=True) + "\n", encoding="utf-8")

    sidecars = kg.load_sidecars(folder) if use_kg_provenance else []

    all_claims: list[dict] = []
    all_defs: list[dict] = []
    sources: list[dict] = []
    fps: dict[str, dict] = {}
    skipped: list[str] = []
    n_kg_reused = 0
    nd_assignments: list[dict] = []

    for p in sorted(folder.rglob("*")):
        if p.is_dir():
            continue
        if out in p.parents or any(part.startswith(".") for part in p.relative_to(folder).parts):
            continue  # skip the index dir and dotfiles/dotdirs
        rel = p.relative_to(folder).as_posix()
        if use_kg_provenance and kg.is_kg_stub(p, folder):
            skipped.append(f"{rel} (kg stub — provenance only)")
            continue
        if p.suffix.lower() not in SUPPORTED:
            skipped.append(rel)
            continue
        # ADR-URN option B: reuse the KG *registry* canonical_urn first (matched by relpath
        # / filename), then a folder-local KG sidecar, else mint under the library namespace.
        reg_urn = consume.reuse_urn(relpath=rel, filename=p.name) if consume else None
        kg_urn = None if reg_urn else (
            kg.provenance_urn_for(rel, sidecars) if use_kg_provenance else None)
        canonical = reg_urn or kg_urn
        urn = canonical or _urn_for(p, profile, namespace=namespace)
        if reg_urn:
            provenance = "kg-registry"
        elif kg_urn:
            provenance = "kg-canonical"
        else:
            provenance = "minted"
        if canonical:
            n_kg_reused += 1
        try:
            res = _extract_file(p, urn, profile)
        except Exception as e:  # a bad/scanned/binary file must not sink the run
            skipped.append(f"{rel} (error: {type(e).__name__})")
            continue
        items = res["items"]
        all_claims.extend(items)
        # P1: seed clean entity-concepts from the FULL extracted text, not claim text
        all_defs.extend(ex.definitions(res.get("text", ""), urn, profile))
        sources.append({"source_urn": urn, "path": rel, "n_items": len(items),
                        "unit_type": res.get("unit_type"), "profile": profile.id,
                        "provenance": provenance, "library": library or "",
                        "canonical_urn": canonical or ""})
        # loop 4: when a consume registry backs this source, READ its jurisdiction +
        # detected_year from the registry row and pass them as nd_context so the
        # fingerprint's nd.jurisdiction / nd.time are populated (not inferred, no
        # classify_domain call). No registry ⇒ nd_context stays None ⇒ nd empty.
        nd_context = None
        if consume is not None:
            prov = consume.provenance_for(relpath=rel, filename=p.name)
            if prov:
                nd_context = {"jurisdiction": prov.get("jurisdiction", ""),
                              "time": prov.get("detected_year", "")}
        if nd_context is None and canonical:
            side = next((s for s in sidecars if s.get("canonical_urn") == canonical), None)
            if side:
                nd_context = {"jurisdiction": side.get("jurisdiction") or "",
                              "time": side.get("year") or ""}
        if nd_context:
            from ..nd import core_system
            core = core_system()
            for axis_id in ("jurisdiction", "time"):
                for value in sorted(fp._coord_set(nd_context, axis_id)):
                    aid = "nda-" + hashlib.sha1(
                        f"{urn}|{axis_id}|{value}".encode()).hexdigest()[:12]
                    nd_assignments.append({
                        "assignment_id": aid, "subject_id": urn,
                        "system_id": core.system_id, "system_version": core.version,
                        "axis_id": axis_id, "value": value,
                        "source_id": canonical or urn,
                        "method": "registry-attested" if consume else "sidecar-attested",
                        "confidence": "", "verification": "attested",
                    })
        fps[urn] = _json_safe(fp.fingerprint(urn, items, profile, nd_context=nd_context))

    g.save_claims(out / "claims.csv", all_claims, profile.id)
    _write_sources(out / "sources.csv", sources)
    _write_csv(out / "definitions.csv", all_defs, DEFINITION_COLUMNS)
    (out / "fingerprints.json").write_text(
        json.dumps(fps, ensure_ascii=False, indent=2), encoding="utf-8")
    from ..nd import save_assignments, save_bindings
    save_assignments(nd_dir / "assignments.csv", nd_assignments)
    save_bindings(nd_dir / "bindings.csv", [])
    # preserve curation output; only create if absent
    if not (out / "concepts.csv").exists():
        g.save_concepts(out / "concepts.csv", [])
    if not (out / "semantic_edges.csv").exists():
        g.save_edges(out / "semantic_edges.csv", [])

    manifest = {
        "folder": str(folder), "profile": profile.id,
        "namespace": namespace or profile.namespace,
        "library": library or "", "catalogue_version": profile.catalogue_version,
        "n_sources": len(sources), "n_claims": len(all_claims),
        "n_definitions": len(all_defs), "n_kg_reused": n_kg_reused,
        "n_skipped": len(skipped), "out": str(out),
        "n_nd_systems": len(nd_registry.systems),
        "n_nd_assignments": len(nd_assignments),
    }
    (out / "index.json").write_text(
        json.dumps({**manifest, "skipped": skipped}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return {**manifest, "skipped": skipped}
