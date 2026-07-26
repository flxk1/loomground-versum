"""versum/materialize.py — additive claims-layer materialization keyed on canonical_urn.

The Versum's ``.versum/`` store keys a source's claims on whatever URN identity resolution
settled for it — a REUSED KG ``canonical_urn`` when the KG already owns provenance, or a
minted path-slug when it does not. This module exports that semantic layer (claims +
concepts + semantic_edges + fingerprints) into a **separate target directory** in a
KG-canonical layout where **every emitted row keys on the source's ``canonical_urn``**
(read from ``sources.csv``'s provenance linkage), never on a path-slug and never on a
filename.

Three invariants make this safe to run against a live KG:

  * **Additive / referencing.** It writes only into ``target_dir`` and carries
    ``canonical_urn`` + ``library`` as *references* back to the KG. It never touches the
    source ``.versum`` store, never shadows the 19-column KG registry, never overwrites
    provenance. The single write door into a Versum stays :mod:`versum.write` +
    ``index_folder`` (loop 6); this module only READS the store.
  * **Canonical-keyed.** A row whose source has no ``canonical_urn`` (a minted, not-yet-
    reconciled source) is SKIPPED with a reported count — never dropped silently and never
    emitted under a path-slug key.
  * **Idempotent.** Output is a pure, deterministic function of the store's content: rows
    are sorted, JSON keys are sorted, no timestamps are written. Re-running on an unchanged
    folder rewrites nothing (byte-identical), so a second call is a no-op.

Domain-neutral: this module names no domain vocabulary. All row shapes are carried through
from the store as-is. No network.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

# The KG-canonical semantic layer written into target_dir. Every table gains a leading
# ``canonical_urn`` + ``library`` key; the remaining columns are carried through from the
# store unchanged (no domain column is named here).
KEY_COLUMNS = ["canonical_urn", "library"]
CLAIMS_FILE = "claims.csv"
CONCEPTS_FILE = "concepts.csv"
EDGES_FILE = "semantic_edges.csv"
FINGERPRINTS_FILE = "fingerprints.json"
MANIFEST_FILE = "materialize.json"


def _versum_dir(folder) -> Path:
    return Path(folder).resolve() / ".versum"


def _read_csv(path: Path):
    """Return ``(fieldnames, rows)`` for a CSV, or ``([], [])`` if it is absent."""
    if not path.exists():
        return [], []
    with open(path, newline="", encoding="utf-8") as fh:
        r = csv.DictReader(fh)
        rows = list(r)
        return (list(r.fieldnames or []), rows)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _csv_bytes(columns, rows) -> bytes:
    """Serialise rows to deterministic CSV bytes (fixed newline, stable column order)."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for row in rows:
        w.writerow({c: ("" if row.get(c) is None else row.get(c)) for c in columns})
    return buf.getvalue().encode("utf-8")


def _json_bytes(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_if_changed(path: Path, data: bytes) -> bool:
    """Write ``data`` only if the file's bytes differ; return True iff it changed.

    Not touching an already-correct file is what makes a re-run a true no-op (stable mtime,
    identical bytes).
    """
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def materialize(folder, target_dir, library=None) -> dict:
    """Export a folder's ``.versum`` semantic layer into ``target_dir``, keyed on canonical_urn.

    Reads the folder's store (``claims.csv`` / ``concepts.csv`` / ``semantic_edges.csv`` /
    ``fingerprints.json`` / ``sources.csv``) and writes a KG-canonical semantic layer into
    ``target_dir`` in which every claim / concept / edge / fingerprint keys on the source's
    ``canonical_urn`` — the provenance linkage recorded in ``sources.csv`` — carrying the
    owning ``library`` alongside.

    A source that carries no ``canonical_urn`` (minted, not yet reconciled to the KG) is
    SKIPPED with a reported count; its claims/fingerprints are not emitted under a path-slug
    key. Concept-to-concept edges (which no single source owns) are likewise counted and not
    emitted into the canonical-keyed claim fabric. The write is additive — the source
    ``.versum`` store is never touched — and idempotent — output is a deterministic function
    of the store, so re-running is a byte-identical no-op.

    Returns a manifest dict with the emitted counts and the skipped counts.
    """
    v = _versum_dir(folder)
    target = Path(target_dir).resolve()
    if target == v:
        raise ValueError(
            "target_dir must not be the source .versum store — materialize is additive "
            "and REFERENCES the store, it never writes back into it")
    target.mkdir(parents=True, exist_ok=True)

    claim_cols, claims = _read_csv(v / CLAIMS_FILE)
    concept_cols, concepts = _read_csv(v / CONCEPTS_FILE)
    edge_cols, edges = _read_csv(v / EDGES_FILE)
    _src_cols, sources = _read_csv(v / "sources.csv")
    fingerprints = _read_json(v / FINGERPRINTS_FILE)

    # source_urn -> (canonical_urn, library). canonical_urn comes from the KG provenance
    # linkage column; the library override is the caller's, else the source's own.
    canon_of: dict[str, str] = {}
    lib_of: dict[str, str] = {}
    for s in sources:
        urn = (s.get("source_urn") or "").strip()
        if not urn:
            continue
        canon_of[urn] = (s.get("canonical_urn") or "").strip()
        lib_of[urn] = (library or s.get("library") or "").strip()

    def _canon_lib_for_source(urn: str):
        return canon_of.get(urn, ""), lib_of.get(urn, (library or "").strip())

    # item_id -> source_urn (to key concepts/edges through the claim they ground)
    src_of_item: dict[str, str] = {}
    for c in claims:
        iid = (c.get("item_id") or "").strip()
        if iid:
            src_of_item[iid] = (c.get("source_urn") or "").strip()

    def _canon_lib_for_item(item_id: str):
        return _canon_lib_for_source(src_of_item.get(item_id, ""))

    # ── claims ───────────────────────────────────────────────────
    out_claims, skipped_claims = [], 0
    for c in claims:
        canon, lib = _canon_lib_for_source((c.get("source_urn") or "").strip())
        if not canon:
            skipped_claims += 1
            continue
        out_claims.append({"canonical_urn": canon, "library": lib, **c})
    out_claims.sort(key=lambda r: (r["canonical_urn"], r.get("item_id", "")))

    # ── concept groundings (concept_id -> {(canonical_urn, library)}) via grounds edges ──
    concept_keys: dict[str, set] = {}
    out_edges, skipped_edges = [], 0
    for e in edges:
        if (e.get("edge_type") or "").strip() != "grounds":
            skipped_edges += 1  # concept↔concept edge: no single source owns it
            continue
        canon, lib = _canon_lib_for_item((e.get("src_id") or "").strip())
        if not canon:
            skipped_edges += 1
            continue
        concept_keys.setdefault((e.get("dst_id") or "").strip(), set()).add((canon, lib))
        out_edges.append({"canonical_urn": canon, "library": lib, **e})
    out_edges.sort(key=lambda r: (r["canonical_urn"], r.get("edge_id", "")))

    # ── concepts (one row per grounding source's canonical_urn) ──
    out_concepts, skipped_concepts = [], 0
    for con in concepts:
        cid = (con.get("concept_id") or "").strip()
        keys = sorted(concept_keys.get(cid, set()))
        if not keys:
            skipped_concepts += 1  # ungrounded concept: no source canonical_urn to key on
            continue
        for canon, lib in keys:
            out_concepts.append({"canonical_urn": canon, "library": lib, **con})
    out_concepts.sort(key=lambda r: (r["canonical_urn"], r.get("concept_id", "")))

    # ── fingerprints (re-keyed by canonical_urn) ─────────────────
    out_fps: dict[str, dict] = {}
    skipped_fps = 0
    for urn in sorted(fingerprints):
        canon, lib = _canon_lib_for_source(urn)
        if not canon:
            skipped_fps += 1
            continue
        fp = dict(fingerprints[urn])
        fp["canonical_urn"] = canon
        fp["library"] = lib
        out_fps[canon] = fp

    claim_out_cols = KEY_COLUMNS + [c for c in claim_cols if c not in KEY_COLUMNS]
    concept_out_cols = KEY_COLUMNS + [c for c in concept_cols if c not in KEY_COLUMNS]
    edge_out_cols = KEY_COLUMNS + [c for c in edge_cols if c not in KEY_COLUMNS]

    manifest = {
        "source_folder": str(Path(folder).resolve()),
        "target_dir": str(target),
        "library": (library or "").strip(),
        "n_sources_total": len(sources),
        "n_sources_with_canonical": sum(1 for u in canon_of.values() if u),
        "n_sources_skipped_no_canonical": sum(1 for u in canon_of.values() if not u),
        "n_claims": len(out_claims),
        "n_claims_skipped_no_canonical": skipped_claims,
        "n_concepts": len(out_concepts),
        "n_concepts_skipped_no_canonical": skipped_concepts,
        "n_edges": len(out_edges),
        "n_edges_skipped_no_canonical": skipped_edges,
        "n_fingerprints": len(out_fps),
        "n_fingerprints_skipped_no_canonical": skipped_fps,
        "skipped_source_urns": sorted(u for u, c in canon_of.items() if not c),
    }

    changed = 0
    changed += _write_if_changed(target / CLAIMS_FILE, _csv_bytes(claim_out_cols, out_claims))
    changed += _write_if_changed(target / CONCEPTS_FILE,
                                 _csv_bytes(concept_out_cols, out_concepts))
    changed += _write_if_changed(target / EDGES_FILE, _csv_bytes(edge_out_cols, out_edges))
    changed += _write_if_changed(target / FINGERPRINTS_FILE, _json_bytes(out_fps))
    changed += _write_if_changed(target / MANIFEST_FILE, _json_bytes(manifest))

    return {**manifest, "n_files_written": changed, "no_op": changed == 0}
