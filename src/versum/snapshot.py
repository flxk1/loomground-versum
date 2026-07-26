"""versum/snapshot.py — graph_version minting (seam K2).

A ``graph_version`` identifies the **materialized semantic graph**: a content digest
over a canonical projection of the by-domain store — every claim row, every
fingerprint, and the nD-system manifest — not over the sync inventory that produced
them. (The 2026-07-21 review of the first cut showed why the inventory is not enough:
an extractor or profile change can alter a claim's text, span, or axes without
changing source bytes or claim count, and the inventory's ``lib::relpath`` keying let
storage arrangement leak into the token.)

Properties the digest must keep (the K2 falsifiers):

  * Stores holding an equivalent materialized graph mint identical versions — the
    projection excludes storage arrangement: library ids, domain directories, file
    paths, and wall-clock fields never enter the digest.
  * Any semantic change mints a new version: a claim's text/span/axes (extraction or
    profile change included), a fingerprint, or nD configuration.

The token is opaque to consumers: compare for equality, never parse. Its concrete form
(``sha256:<64-hex>`` over the ``materialized-graph/v1`` projection) is a Versum
implementation detail until the joint wire spec in the language repo fixes a shape.
The wire-level bound (non-empty, at most ``interop.MAX_GRAPH_VERSION_LENGTH``
characters) is enforced where it belongs: at mint (``reasoning``) and at decode
(``interop``), via ``interop.valid_graph_version`` — this module mints conforming
tokens by construction and carries no validator of its own.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

GRAPH_VERSION_FILE = "_graph_version.json"
ND_SYSTEMS_FILE = "_nd_systems.json"
INPUTS_ID = "materialized-graph/v2"

#: Storage-arrangement keys stripped from projected rows/objects: ``library`` names the
#: ingest lane, not the content (the same source under another library id is the same
#: semantic fact). Paths and domains never appear in claim rows; sources.csv (which
#: does carry paths) is excluded from the projection entirely.
_ARRANGEMENT_KEYS = ("library",)


def _canonical_rows(rows) -> list:
    """Claim rows minus storage arrangement, deterministically ordered."""
    projected = [
        {k: ("" if v is None else str(v)) for k, v in row.items()
         if k not in _ARRANGEMENT_KEYS}
        for row in rows
    ]
    return sorted(projected, key=lambda r: json.dumps(r, sort_keys=True))


def mint_graph_version(kg_root) -> str:
    """Digest the store's materialized graph into a ``graph_version`` token.

    Reads the by-domain store under ``kg_root``: all ``claims.csv`` rows (across
    domains — the domain directory is arrangement, not content), all
    ``fingerprints.json`` entries, and ``_nd_systems.json`` when present. O(store
    size) per mint; minted once per sync pass.
    """
    from .sync import BY_DOMAIN, _read_rows  # local import — sync imports us too

    root = Path(kg_root)
    base = root / BY_DOMAIN

    claims = []
    fingerprints = {}
    if base.exists():
        for table in sorted(base.glob("*/claims.csv")):
            _cols, rows = _read_rows(table)
            claims.extend(rows)
        for fp_path in sorted(base.glob("*/fingerprints.json")):
            try:
                fps = json.loads(fp_path.read_text(encoding="utf-8")) or {}
            except Exception:
                fps = {}
            for urn, fp in fps.items():
                fingerprints[urn] = {k: v for k, v in (fp or {}).items()
                                     if k not in _ARRANGEMENT_KEYS}

    nd_manifest = None
    nd_path = root / ND_SYSTEMS_FILE
    if nd_path.exists():
        try:
            nd_manifest = json.loads(nd_path.read_text(encoding="utf-8"))
        except Exception:
            nd_manifest = None

    from .ingestion import load_dimensioned_subgraphs
    dimensioned_subgraphs = [
        graph.to_dict() for graph in load_dimensioned_subgraphs(root)
    ]

    payload = json.dumps(
        {"inputs": INPUTS_ID,
         "claims": _canonical_rows(claims),
         "fingerprints": fingerprints,
         "nd_systems": nd_manifest,
         "dimensioned_subgraphs": dimensioned_subgraphs},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stamp_graph_version(kg_root, version: str) -> None:
    """Persist the minted version at ``<kg_root>/_graph_version.json``."""
    path = Path(kg_root) / GRAPH_VERSION_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"graph_version": version, "inputs": INPUTS_ID},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


def current_graph_version(kg_root) -> str:
    """The last stamped version, or ``""`` when the store has never been synced."""
    path = Path(kg_root) / GRAPH_VERSION_FILE
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(data.get("graph_version", ""))


def require_graph_version(kg_root) -> str:
    """The stamped version, for emitting store-backed wire records; raises if absent.

    ``candidate_from_claim`` can only refuse an *empty* token — it never sees
    the store, so it cannot prove a non-empty one was minted here. A producer
    emitting records for a store therefore obtains the token through this
    function (never invents one); that discharge is what binds the record to a
    snapshot Versum actually minted.
    """
    version = current_graph_version(kg_root)
    if not version:
        raise ValueError(
            f"store at {kg_root} has no stamped graph_version — run a sync first")
    return version

