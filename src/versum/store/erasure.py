"""versum/store/erasure.py — logical delete and GDPR Art.17 purge over the KG store.

Two erasure grades, both recorded **through the append-only event log**
(:mod:`versum.events`) so history is never silently rewritten:

  * **logical delete** — tombstones a node (a claim or a concept) or a whole source so it
    stops appearing in every read (snapshot / claims / concepts / edges / search) while its
    content and its audit trail remain intact, recoverable via :func:`restore`.
  * **purge** — the hard GDPR Art.17 erasure: the node's / source's content is physically
    removed from the live projection (``by-domain/*/claims.csv``, ``sources.csv``,
    ``fingerprints.json``, curated concepts) and only a signed tombstone marker is left for
    integrity. A purge is not recoverable.

The tombstone set is itself a projection (``<kg_root>/_erasure.json``) that folds the
erasure events out of the log; reads consult it through :func:`load_tombstones`. Ported from
RVND's WorkspaceMemory erasure layer (``delete`` / ``delete_document`` / ``purge_pair`` /
``purge_document``) so RVND can retire its parallel store.

A node id is the same ``"<type>:<id>"`` token a search hit carries
(:attr:`versum.store.retrieve.Doc.doc_id`) — ``"claim:<item_id>"`` or
``"concept:<concept_id>"`` — so a caller can erase a hit directly.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path

ERASURE_FILE = "_erasure.json"
ERASURE_SCHEMA = "loomground.versum.erasure/v1"

DELETE_EVENT = "node.deleted"
RESTORE_EVENT = "node.restored"
PURGE_EVENT = "node.purged"
SOURCE_DELETE_EVENT = "source.deleted"
SOURCE_PURGE_EVENT = "source.purged"
ERASURE_EVENT_TYPES = frozenset({
    DELETE_EVENT, RESTORE_EVENT, PURGE_EVENT, SOURCE_DELETE_EVENT, SOURCE_PURGE_EVENT})

_NODE_TYPES = ("claim", "concept")


# ── the read model: a tombstone set consulted by every read ───────
@dataclass(frozen=True)
class Tombstones:
    """The erasure state a read consults: which nodes/sources must stay hidden.

    Both grades hide a node from reads; only :attr:`purged_nodes` / :attr:`purged_sources`
    have had their content physically removed. ``records`` is the ordered audit trail.
    """

    deleted_nodes: frozenset = frozenset()
    purged_nodes: frozenset = frozenset()
    deleted_sources: frozenset = frozenset()
    purged_sources: frozenset = frozenset()
    records: tuple = ()

    @property
    def hidden_nodes(self) -> frozenset:
        """Every node id excluded from reads (logically deleted OR purged)."""
        return self.deleted_nodes | self.purged_nodes

    @property
    def hidden_sources(self) -> frozenset:
        """Every source canonical_urn excluded from reads (deleted OR purged)."""
        return self.deleted_sources | self.purged_sources

    def hides(self, doc_id: str, canonical_urn: str = "") -> bool:
        """True when a document with this id / source must be excluded from reads."""
        return (doc_id in self.hidden_nodes
                or (bool(canonical_urn) and canonical_urn in self.hidden_sources))


def load_tombstones(kg_root) -> Tombstones:
    """Read the erasure projection (``_erasure.json``); an absent file means nothing is erased.

    Dependency-free (stdlib only) so the read path never pulls the write machinery.
    """
    path = Path(kg_root) / ERASURE_FILE
    if not path.exists():
        return Tombstones()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return Tombstones()
    return Tombstones(
        deleted_nodes=frozenset(data.get("deleted_nodes", [])),
        purged_nodes=frozenset(data.get("purged_nodes", [])),
        deleted_sources=frozenset(data.get("deleted_sources", [])),
        purged_sources=frozenset(data.get("purged_sources", [])),
        records=tuple(data.get("records", [])),
    )


# ── node-id parsing ───────────────────────────────────────────────
def _parse_node_id(node_id: str) -> tuple[str, str]:
    """Split ``"claim:<id>"`` / ``"concept:<id>"`` into ``(target_type, target_id)``."""
    if not isinstance(node_id, str) or ":" not in node_id:
        raise ValueError(f"node_id must be 'claim:<id>' or 'concept:<id>', got {node_id!r}")
    target_type, target_id = node_id.split(":", 1)
    if target_type not in _NODE_TYPES:
        raise ValueError(f"unknown node type {target_type!r} (expected one of {_NODE_TYPES})")
    if not target_id:
        raise ValueError(f"node_id {node_id!r} carries no id")
    return target_type, target_id


# ── CSV projection helpers (header-agnostic; both store layouts) ──
def _read_csv(path: Path):
    """Return ``(fieldnames, rows)`` for a CSV — NUL-stripped, ``([], [])`` if absent."""
    if not path.exists():
        return [], []
    raw = path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")
    reader = csv.DictReader(io.StringIO(raw))
    rows = list(reader)
    return list(reader.fieldnames or []), rows


def _write_csv(path: Path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore",
                                lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: ("" if row.get(c) is None else row.get(c))
                             for c in fieldnames})


def _claim_csv_paths(root: Path) -> list[Path]:
    bd = root / "by-domain"
    if bd.is_dir():
        return sorted(bd.glob("*/claims.csv"))
    flat = root / "claims.csv"
    return [flat] if flat.exists() else []


def _source_csv_paths(root: Path) -> list[Path]:
    bd = root / "by-domain"
    if bd.is_dir():
        return sorted(bd.glob("*/sources.csv"))
    flat = root / "sources.csv"
    return [flat] if flat.exists() else []


def _concept_csv_paths(root: Path) -> list[Path]:
    bd = root / "by-domain"
    if bd.is_dir():
        return sorted(bd.glob("*/concepts.csv"))
    flat = root / "concepts.csv"
    return [flat] if flat.exists() else []


def _fingerprint_paths(root: Path) -> list[Path]:
    bd = root / "by-domain"
    if bd.is_dir():
        return sorted(bd.glob("*/fingerprints.json"))
    flat = root / "fingerprints.json"
    return [flat] if flat.exists() else []


def _row_urn(row: dict) -> str:
    return (row.get("canonical_urn") or row.get("source_urn") or "").strip()


def _canonical_urn_for_claim(root: Path, item_id: str) -> str:
    for path in _claim_csv_paths(root):
        _cols, rows = _read_csv(path)
        for row in rows:
            if (row.get("item_id") or "").strip() == item_id:
                return _row_urn(row)
    return ""


def _claim_rows_for(root: Path, *, item_id=None, canonical_urn=None) -> list[dict]:
    out: list[dict] = []
    for path in _claim_csv_paths(root):
        _cols, rows = _read_csv(path)
        for row in rows:
            if item_id is not None and (row.get("item_id") or "").strip() != item_id:
                continue
            if canonical_urn is not None and _row_urn(row) != canonical_urn:
                continue
            out.append(dict(row))
    return out


def _concept_rows_for(root: Path, concept_id: str) -> list[dict]:
    out: list[dict] = []
    for path in _concept_csv_paths(root):
        _cols, rows = _read_csv(path)
        out.extend(dict(r) for r in rows
                   if (r.get("concept_id") or "").strip() == concept_id)
    canon = root / "canon.json"
    if canon.exists():
        try:
            data = json.loads(canon.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        out.extend(dict(c) for c in data.get("concepts", [])
                   if (c.get("concept_id") or "").strip() == concept_id)
    return out


# ── content strippers (the hard Art.17 removal) ──────────────────
def _strip_claim_rows(root, *, item_id) -> int:
    root = Path(root)
    removed = 0
    for path in _claim_csv_paths(root):
        cols, rows = _read_csv(path)
        kept = [r for r in rows if (r.get("item_id") or "").strip() != item_id]
        if len(kept) != len(rows):
            removed += len(rows) - len(kept)
            _write_csv(path, cols, kept)
    return removed


def _strip_concept(root, *, concept_id) -> int:
    root = Path(root)
    removed = 0
    for path in _concept_csv_paths(root):
        cols, rows = _read_csv(path)
        kept = [r for r in rows if (r.get("concept_id") or "").strip() != concept_id]
        if len(kept) != len(rows):
            removed += len(rows) - len(kept)
            _write_csv(path, cols, kept)
    canon = root / "canon.json"
    if canon.exists():
        try:
            data = json.loads(canon.read_text(encoding="utf-8"))
        except Exception:
            data = None
        if isinstance(data, dict) and isinstance(data.get("concepts"), list):
            kept = [c for c in data["concepts"]
                    if (c.get("concept_id") or "").strip() != concept_id]
            if len(kept) != len(data["concepts"]):
                removed += len(data["concepts"]) - len(kept)
                data["concepts"] = kept
                canon.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                            sort_keys=True) + "\n", encoding="utf-8")
    return removed


def _strip_source(root, canonical_urn) -> int:
    """Physically remove a source's claim rows, source row, and fingerprint."""
    root = Path(root)
    removed = 0
    for path in _claim_csv_paths(root):
        cols, rows = _read_csv(path)
        kept = [r for r in rows if _row_urn(r) != canonical_urn]
        if len(kept) != len(rows):
            removed += len(rows) - len(kept)
            _write_csv(path, cols, kept)
    for path in _source_csv_paths(root):
        cols, rows = _read_csv(path)
        kept = [r for r in rows if _row_urn(r) != canonical_urn]
        if len(kept) != len(rows):
            _write_csv(path, cols, kept)
    for path in _fingerprint_paths(root):
        try:
            fps = json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception:
            fps = {}
        if isinstance(fps, dict) and canonical_urn in fps:
            fps.pop(canonical_urn, None)
            path.write_text(json.dumps(fps, ensure_ascii=False, indent=2,
                                       sort_keys=True) + "\n", encoding="utf-8")
    return removed


# ── the erasure projection (folded from the log) ─────────────────
def _empty_state() -> dict:
    return {"deleted_nodes": set(), "purged_nodes": set(),
            "deleted_sources": set(), "purged_sources": set(), "records": []}


def _fold_event(state: dict, event: dict) -> None:
    """Apply one erasure event to the accumulating projection state (in place)."""
    etype = event.get("event_type")
    if etype not in ERASURE_EVENT_TYPES:
        return
    payload = event.get("payload") or {}
    node_id = payload.get("node_id", "")
    urn = payload.get("canonical_urn", "")
    if etype == DELETE_EVENT:
        state["deleted_nodes"].add(node_id)
        state["purged_nodes"].discard(node_id)
    elif etype == RESTORE_EVENT:
        if node_id:
            state["deleted_nodes"].discard(node_id)
        if urn:
            state["deleted_sources"].discard(urn)
    elif etype == PURGE_EVENT:
        state["deleted_nodes"].discard(node_id)
        state["purged_nodes"].add(node_id)
    elif etype == SOURCE_DELETE_EVENT:
        state["deleted_sources"].add(urn)
        state["purged_sources"].discard(urn)
    elif etype == SOURCE_PURGE_EVENT:
        state["deleted_sources"].discard(urn)
        state["purged_sources"].add(urn)
    state["records"].append({
        "grade": etype, "node_id": node_id, "canonical_urn": urn,
        "target_type": payload.get("target_type", ""),
        "target_id": payload.get("target_id", ""),
        "reason": payload.get("reason", ""), "actor": payload.get("actor", ""),
        "affected_claim_ids": list(payload.get("affected_claim_ids", [])),
        "content_digest": payload.get("content_digest", ""),
        "event_id": event.get("event_id", ""), "sequence": event.get("sequence"),
        "observed_at": event.get("observed_at", ""),
    })


def _write_state(root: Path, state: dict) -> dict:
    payload = {
        "schema": ERASURE_SCHEMA,
        "deleted_nodes": sorted(state["deleted_nodes"]),
        "purged_nodes": sorted(state["purged_nodes"]),
        "deleted_sources": sorted(state["deleted_sources"]),
        "purged_sources": sorted(state["purged_sources"]),
        "records": state["records"],
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / ERASURE_FILE).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return payload


def rebuild_erasure_projection(kg_root) -> dict:
    """Refold ``_erasure.json`` from the event log — a deterministic K3-style projection."""
    from ..events import read_events

    root = Path(kg_root)
    state = _empty_state()
    saw = False
    for event in read_events(root):
        if event.get("event_type") in ERASURE_EVENT_TYPES:
            saw = True
            _fold_event(state, event)
    if saw or (root / ERASURE_FILE).exists():
        return _write_state(root, state)
    return {"schema": ERASURE_SCHEMA, "deleted_nodes": [], "purged_nodes": [],
            "deleted_sources": [], "purged_sources": [], "records": []}


# ── the public erasure operations ────────────────────────────────
def _append(root: Path, event_type: str, object_id: str, payload: dict, observed_at):
    from ..events import EventLog

    with EventLog(root) as log:
        return log.append(event_type, payload.get("_object_type", "node"),
                          object_id, {k: v for k, v in payload.items()
                                      if k != "_object_type"}, observed_at=observed_at)


def _node_object_id(node_id: str) -> str:
    return node_id


def _source_object_id(canonical_urn: str) -> str:
    return f"source-erasure:{canonical_urn}"


def delete(kg_root, node_id: str, *, reason: str = "", actor: str = "",
           observed_at: str | None = None) -> dict:
    """Logically delete (tombstone) one claim or concept.

    The node stops appearing in every read but its content and audit trail remain, so it can
    be recovered with :func:`restore`. Recorded as a signed ``node.deleted`` event.
    """
    target_type, target_id = _parse_node_id(node_id)
    root = Path(kg_root)
    canonical_urn = (_canonical_urn_for_claim(root, target_id)
                     if target_type == "claim" else "")
    payload = {
        "node_id": node_id, "target_type": target_type, "target_id": target_id,
        "canonical_urn": canonical_urn, "reason": reason, "actor": actor,
        "recoverable": True,
        "affected_claim_ids": [target_id] if target_type == "claim" else [],
    }
    event = _append(root, DELETE_EVENT, _node_object_id(node_id), payload, observed_at)
    rebuild_erasure_projection(root)
    return {"node_id": node_id, "grade": "deleted", "recoverable": True,
            "canonical_urn": canonical_urn, "event_id": event["event_id"]}


def restore(kg_root, node_id: str, *, actor: str = "",
            observed_at: str | None = None) -> dict:
    """Undo a logical :func:`delete`. Raises if the node was never deleted or was purged."""
    _parse_node_id(node_id)
    root = Path(kg_root)
    tombs = load_tombstones(root)
    if node_id in tombs.purged_nodes:
        raise ValueError(f"{node_id!r} was purged (Art.17) and cannot be restored")
    if node_id not in tombs.deleted_nodes:
        raise ValueError(f"{node_id!r} is not logically deleted")
    payload = {"node_id": node_id, "actor": actor, "affected_claim_ids": []}
    event = _append(root, RESTORE_EVENT, _node_object_id(node_id), payload, observed_at)
    rebuild_erasure_projection(root)
    return {"node_id": node_id, "grade": "restored", "event_id": event["event_id"]}


def purge(kg_root, node_id: str, *, reason: str = "", actor: str = "",
          observed_at: str | None = None) -> dict:
    """Hard GDPR Art.17 erasure of one claim or concept.

    The node's content is physically removed from the live projection; a signed
    ``node.purged`` tombstone (carrying a digest of the removed content) is left for
    integrity. Not recoverable.
    """
    from ..events import object_digest

    target_type, target_id = _parse_node_id(node_id)
    root = Path(kg_root)
    if target_type == "claim":
        rows = _claim_rows_for(root, item_id=target_id)
        canonical_urn = _row_urn(rows[0]) if rows else ""
    else:
        rows = _concept_rows_for(root, target_id)
        canonical_urn = ""
    payload = {
        "node_id": node_id, "target_type": target_type, "target_id": target_id,
        "canonical_urn": canonical_urn, "reason": reason, "actor": actor,
        "recoverable": False, "content_digest": object_digest(rows),
        "affected_claim_ids": [target_id] if target_type == "claim" else [],
    }
    event = _append(root, PURGE_EVENT, _node_object_id(node_id), payload, observed_at)
    if target_type == "claim":
        removed = _strip_claim_rows(root, item_id=target_id)
    else:
        removed = _strip_concept(root, concept_id=target_id)
    rebuild_erasure_projection(root)
    return {"node_id": node_id, "grade": "purged", "recoverable": False,
            "canonical_urn": canonical_urn, "content_digest": payload["content_digest"],
            "rows_removed": removed, "event_id": event["event_id"]}


def delete_by_source(kg_root, canonical_urn: str, *, reason: str = "", actor: str = "",
                     observed_at: str | None = None) -> dict:
    """Logically delete every node of one source document (RVND ``delete_document``).

    Every claim carrying ``canonical_urn`` is tombstoned via a single signed
    ``source.deleted`` event; content and audit trail remain, recoverable through
    :func:`restore_source`.
    """
    root = Path(kg_root)
    rows = _claim_rows_for(root, canonical_urn=canonical_urn)
    affected = sorted({(r.get("item_id") or "").strip() for r in rows if r.get("item_id")})
    payload = {
        "node_id": "", "canonical_urn": canonical_urn, "reason": reason, "actor": actor,
        "recoverable": True, "affected_claim_ids": affected, "_object_type": "source",
    }
    event = _append(root, SOURCE_DELETE_EVENT, _source_object_id(canonical_urn), payload,
                    observed_at)
    rebuild_erasure_projection(root)
    return {"canonical_urn": canonical_urn, "grade": "deleted", "recoverable": True,
            "affected_claim_ids": affected, "event_id": event["event_id"]}


def restore_source(kg_root, canonical_urn: str, *, actor: str = "",
                   observed_at: str | None = None) -> dict:
    """Undo a :func:`delete_by_source`. Raises if the source was never deleted or was purged."""
    root = Path(kg_root)
    tombs = load_tombstones(root)
    if canonical_urn in tombs.purged_sources:
        raise ValueError(f"source {canonical_urn!r} was purged and cannot be restored")
    if canonical_urn not in tombs.deleted_sources:
        raise ValueError(f"source {canonical_urn!r} is not logically deleted")
    payload = {"node_id": "", "canonical_urn": canonical_urn, "actor": actor,
               "affected_claim_ids": [], "_object_type": "source"}
    event = _append(root, RESTORE_EVENT, _source_object_id(canonical_urn), payload,
                    observed_at)
    rebuild_erasure_projection(root)
    return {"canonical_urn": canonical_urn, "grade": "restored",
            "event_id": event["event_id"]}


def purge_by_source(kg_root, canonical_urn: str, *, reason: str = "", actor: str = "",
                    observed_at: str | None = None) -> dict:
    """Hard GDPR Art.17 erasure of a whole source document (RVND ``purge_document``).

    Every claim row, the source row, and the fingerprint for ``canonical_urn`` are
    physically removed; a signed ``source.purged`` tombstone (with a content digest) is
    left for integrity. Not recoverable.
    """
    from ..events import object_digest

    root = Path(kg_root)
    rows = _claim_rows_for(root, canonical_urn=canonical_urn)
    affected = sorted({(r.get("item_id") or "").strip() for r in rows if r.get("item_id")})
    payload = {
        "node_id": "", "canonical_urn": canonical_urn, "reason": reason, "actor": actor,
        "recoverable": False, "content_digest": object_digest(rows),
        "affected_claim_ids": affected, "_object_type": "source",
    }
    event = _append(root, SOURCE_PURGE_EVENT, _source_object_id(canonical_urn), payload,
                    observed_at)
    removed = _strip_source(root, canonical_urn)
    rebuild_erasure_projection(root)
    return {"canonical_urn": canonical_urn, "grade": "purged", "recoverable": False,
            "content_digest": payload["content_digest"], "rows_removed": removed,
            "affected_claim_ids": affected, "event_id": event["event_id"]}
