"""versum/store/distribution.py — the asymmetric publish / distribution layer.

The folder hierarchy is asymmetric. A folder's read view always includes its **own**
store plus every **descendant** folder's store (memory flows UP; siblings and ancestors
are out of scope by construction — see :mod:`versum.store.hierarchy`). The one exception
is this module: a claim or a whole source that an ancestor folder has explicitly
**published** flows DOWN to every descendant.

Publication is recorded **through the append-only event log** (:mod:`versum.events`), the
same idiom as erasure (:mod:`versum.store.erasure`) — history is never rewritten:

  * :func:`publish` marks a node (``"claim:<id>"`` / ``"concept:<id>"``) or a whole source
    (a ``canonical_urn``) as distributed to descendants.
  * :func:`unpublish` revokes it. The item stops flowing down on the next read.

The published set is a projection (``<kg_root>/_distribution.json``) folded out of the
distribution events by :func:`rebuild_distribution_projection`; reads consult it through
:func:`load_distribution`. Erasure always wins: a tombstoned item is dropped from the read
projection before the publish filter runs, so an erased node is never distributed even if it
was published earlier (see :func:`versum.store.hierarchy.aggregate_docs`).

Ported from RVND's ``WorkspaceMemory.publish`` / ``unpublish`` (the B5 distributed-memory
path) so RVND can retire the last of its parallel store.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import erasure

DISTRIBUTION_FILE = "_distribution.json"
DISTRIBUTION_SCHEMA = "loomground.versum.distribution/v1"

PUBLISH_EVENT = "node.published"
UNPUBLISH_EVENT = "node.unpublished"
SOURCE_PUBLISH_EVENT = "source.published"
SOURCE_UNPUBLISH_EVENT = "source.unpublished"
DISTRIBUTION_EVENT_TYPES = frozenset({
    PUBLISH_EVENT, UNPUBLISH_EVENT, SOURCE_PUBLISH_EVENT, SOURCE_UNPUBLISH_EVENT})

#: The only distribution scope RVND ever used; other values are reserved for future use.
DEFAULT_SCOPE = "descendants"

_NODE_TYPES = ("claim", "concept")


# ── the read model: which nodes/sources flow DOWN to descendants ───
@dataclass(frozen=True)
class Distribution:
    """The publication state a descendant read consults: what an ancestor shares downward.

    ``records`` is the ordered audit trail folded from the distribution events.
    """

    published_nodes: frozenset = frozenset()
    published_sources: frozenset = frozenset()
    records: tuple = ()

    def distributes(self, doc_id: str, canonical_urn: str = "") -> bool:
        """True when this node id / source is published to descendants."""
        return (doc_id in self.published_nodes
                or (bool(canonical_urn) and canonical_urn in self.published_sources))


def load_distribution(kg_root) -> Distribution:
    """Read the distribution projection (``_distribution.json``); an absent file means nothing
    is published. Dependency-free (stdlib only) so the read path never pulls the write machinery.
    """
    path = Path(kg_root) / DISTRIBUTION_FILE
    if not path.exists():
        return Distribution()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return Distribution()
    return Distribution(
        published_nodes=frozenset(data.get("published_nodes", [])),
        published_sources=frozenset(data.get("published_sources", [])),
        records=tuple(data.get("records", [])),
    )


# ── target parsing (node id vs. source urn) ──────────────────────
def _is_node_id(target: str) -> bool:
    """True when ``target`` is a ``"claim:<id>"`` / ``"concept:<id>"`` node id.

    A source is a bare ``canonical_urn`` (e.g. ``"urn:a"``); its prefix is not a node type,
    so it is routed to the source path instead.
    """
    return (isinstance(target, str) and ":" in target
            and target.split(":", 1)[0] in _NODE_TYPES)


# ── the distribution projection (folded from the log) ─────────────
def _empty_state() -> dict:
    return {"published_nodes": set(), "published_sources": set(), "records": []}


def _fold_event(state: dict, event: dict) -> None:
    """Apply one distribution event to the accumulating projection state (in place)."""
    etype = event.get("event_type")
    if etype not in DISTRIBUTION_EVENT_TYPES:
        return
    payload = event.get("payload") or {}
    node_id = payload.get("node_id", "")
    urn = payload.get("canonical_urn", "")
    if etype == PUBLISH_EVENT:
        state["published_nodes"].add(node_id)
    elif etype == UNPUBLISH_EVENT:
        state["published_nodes"].discard(node_id)
    elif etype == SOURCE_PUBLISH_EVENT:
        state["published_sources"].add(urn)
    elif etype == SOURCE_UNPUBLISH_EVENT:
        state["published_sources"].discard(urn)
    state["records"].append({
        "grade": etype, "node_id": node_id, "canonical_urn": urn,
        "target_type": payload.get("target_type", ""),
        "target_id": payload.get("target_id", ""),
        "scope": payload.get("scope", ""),
        "reason": payload.get("reason", ""), "actor": payload.get("actor", ""),
        "affected_claim_ids": list(payload.get("affected_claim_ids", [])),
        "event_id": event.get("event_id", ""), "sequence": event.get("sequence"),
        "observed_at": event.get("observed_at", ""),
    })


def _write_state(root: Path, state: dict) -> dict:
    payload = {
        "schema": DISTRIBUTION_SCHEMA,
        "published_nodes": sorted(state["published_nodes"]),
        "published_sources": sorted(state["published_sources"]),
        "records": state["records"],
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / DISTRIBUTION_FILE).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return payload


def rebuild_distribution_projection(kg_root) -> dict:
    """Refold ``_distribution.json`` from the event log — a deterministic K3-style projection."""
    from ..events import read_events

    root = Path(kg_root)
    state = _empty_state()
    saw = False
    for event in read_events(root):
        if event.get("event_type") in DISTRIBUTION_EVENT_TYPES:
            saw = True
            _fold_event(state, event)
    if saw or (root / DISTRIBUTION_FILE).exists():
        return _write_state(root, state)
    return {"schema": DISTRIBUTION_SCHEMA, "published_nodes": [], "published_sources": [],
            "records": []}


# ── event append (mirrors erasure._append) ───────────────────────
def _append(root: Path, event_type: str, object_id: str, payload: dict, observed_at):
    from ..events import EventLog

    with EventLog(root) as log:
        return log.append(event_type, payload.get("_object_type", "node"),
                          object_id, {k: v for k, v in payload.items()
                                      if k != "_object_type"}, observed_at=observed_at)


def _source_object_id(canonical_urn: str) -> str:
    return f"source-distribution:{canonical_urn}"


def _check_scope(scope: str) -> None:
    if scope != DEFAULT_SCOPE:
        raise ValueError(
            f"distribution scope must be {DEFAULT_SCOPE!r} (got {scope!r}); "
            f"other scopes are reserved for future use")


# ── the public distribution operations ───────────────────────────
def publish(kg_root, target: str, *, scope: str = DEFAULT_SCOPE, reason: str = "",
            actor: str = "", observed_at: str | None = None) -> dict:
    """Publish one node (``"claim:<id>"`` / ``"concept:<id>"``) or a whole source
    (a ``canonical_urn``) so it flows DOWN to every descendant folder.

    ``target`` is auto-routed: a ``claim:``/``concept:`` prefix marks a node; anything else
    is treated as a source ``canonical_urn`` (equivalent to :func:`publish_source`). Recorded
    as a signed ``node.published`` / ``source.published`` event; history is never rewritten.
    """
    _check_scope(scope)
    if _is_node_id(target):
        return _publish_node(Path(kg_root), target, scope, reason, actor, observed_at)
    return publish_source(kg_root, target, scope=scope, reason=reason, actor=actor,
                          observed_at=observed_at)


def unpublish(kg_root, target: str, *, reason: str = "", actor: str = "",
              observed_at: str | None = None) -> dict:
    """Revoke a previously :func:`publish`-ed node or source; it stops flowing down on the
    next read. Recorded as a signed ``node.unpublished`` / ``source.unpublished`` event.
    Lenient by design — revoking something never published is a harmless no-op marker.
    """
    if _is_node_id(target):
        return _unpublish_node(Path(kg_root), target, reason, actor, observed_at)
    return unpublish_source(kg_root, target, reason=reason, actor=actor,
                            observed_at=observed_at)


def _publish_node(root: Path, node_id: str, scope: str, reason: str, actor: str,
                  observed_at) -> dict:
    target_type, target_id = erasure._parse_node_id(node_id)
    canonical_urn = (erasure._canonical_urn_for_claim(root, target_id)
                     if target_type == "claim" else "")
    payload = {
        "node_id": node_id, "target_type": target_type, "target_id": target_id,
        "canonical_urn": canonical_urn, "scope": scope, "reason": reason, "actor": actor,
        "affected_claim_ids": [target_id] if target_type == "claim" else [],
    }
    event = _append(root, PUBLISH_EVENT, node_id, payload, observed_at)
    rebuild_distribution_projection(root)
    return {"node_id": node_id, "grade": "published", "scope": scope,
            "canonical_urn": canonical_urn, "event_id": event["event_id"]}


def _unpublish_node(root: Path, node_id: str, reason: str, actor: str, observed_at) -> dict:
    target_type, target_id = erasure._parse_node_id(node_id)
    payload = {
        "node_id": node_id, "target_type": target_type, "target_id": target_id,
        "reason": reason, "actor": actor,
        "affected_claim_ids": [target_id] if target_type == "claim" else [],
    }
    event = _append(root, UNPUBLISH_EVENT, node_id, payload, observed_at)
    rebuild_distribution_projection(root)
    return {"node_id": node_id, "grade": "unpublished", "event_id": event["event_id"]}


def publish_source(kg_root, canonical_urn: str, *, scope: str = DEFAULT_SCOPE,
                   reason: str = "", actor: str = "", observed_at: str | None = None) -> dict:
    """Publish every claim of one source document to descendants (RVND source-level publish).

    Every claim carrying ``canonical_urn`` flows down via a single signed ``source.published``
    event; the pair bodies stay in this folder's store — nothing is duplicated.
    """
    _check_scope(scope)
    root = Path(kg_root)
    rows = erasure._claim_rows_for(root, canonical_urn=canonical_urn)
    affected = sorted({(r.get("item_id") or "").strip() for r in rows if r.get("item_id")})
    payload = {
        "node_id": "", "canonical_urn": canonical_urn, "scope": scope, "reason": reason,
        "actor": actor, "affected_claim_ids": affected, "_object_type": "source",
    }
    event = _append(root, SOURCE_PUBLISH_EVENT, _source_object_id(canonical_urn), payload,
                    observed_at)
    rebuild_distribution_projection(root)
    return {"canonical_urn": canonical_urn, "grade": "published", "scope": scope,
            "affected_claim_ids": affected, "event_id": event["event_id"]}


def unpublish_source(kg_root, canonical_urn: str, *, reason: str = "", actor: str = "",
                     observed_at: str | None = None) -> dict:
    """Revoke a :func:`publish_source`. The source's claims stop flowing down on next read."""
    root = Path(kg_root)
    rows = erasure._claim_rows_for(root, canonical_urn=canonical_urn)
    affected = sorted({(r.get("item_id") or "").strip() for r in rows if r.get("item_id")})
    payload = {
        "node_id": "", "canonical_urn": canonical_urn, "reason": reason, "actor": actor,
        "affected_claim_ids": affected, "_object_type": "source",
    }
    event = _append(root, SOURCE_UNPUBLISH_EVENT, _source_object_id(canonical_urn), payload,
                    observed_at)
    rebuild_distribution_projection(root)
    return {"canonical_urn": canonical_urn, "grade": "unpublished",
            "affected_claim_ids": affected, "event_id": event["event_id"]}
