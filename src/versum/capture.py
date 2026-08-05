"""Runtime knowledge capture — a source-less write door into the Versum sink.

The canonical Versum write door, :class:`versum.ingestion.subgraph.DimensionedSubgraphSink`,
is *file*-oriented: it demands a source ``content_digest`` (the sha256 of source bytes),
a non-empty ``evidence[]`` with a real ``locator`` into that source, and grammar-lowered
nodes/relations. Runtime knowledge produced by an actor — a fact it observed, an inference
it walked — has no source file and no grounding span. This module builds a *valid*
dimensioned-subgraph envelope for such runtime knowledge and writes it through the **same**
sink, so the result is searchable through the existing
:func:`versum.store.retrieve.from_dimensioned_store` read path and is subject to the same
erasure / distribution / hierarchy machinery. The sink's contract and the file-ingest path
are untouched; this is purely additive.

Runtime knowledge is a **distinct, explicitly-marked provenance class**, not a span-grounded
one. Versum's charter is span-grounded knowledge — a node whose claim is anchored to bytes in
a source via an evidence locator. A runtime fact has no such anchor: it is *asserted by an
actor*. Rather than manufacture a synthetic source/evidence digest out of the assertion itself
(which would silently masquerade as grounding), every runtime node and relation is stamped
``grounding="runtime"`` and the provenance digests are runtime *markers*, never a hash of the
asserted knowledge. A reader/consumer can therefore always tell a runtime-asserted node from a
span-grounded one, and nothing in a runtime envelope claims a grounding it does not have.

Runtime envelope conventions
----------------------------
Every function below lowers runtime knowledge into an envelope that passes
:meth:`versum.ingestion.subgraph.DimensionedSubgraph.from_dict` unchanged:

* **source** — a runtime source shared by everything a given actor asserts::

      source_id      = "runtime:<slug(actor)>"
      content_digest = sha256(<runtime marker>:source:<source_id>)

  The ``runtime:`` namespace declares the class; the digest is the *identity* of the runtime
  source (the actor's runtime channel), **not** a digest of the asserted knowledge and never a
  file digest. It exists only because the sink requires a ``sha256:<64hex>`` bound to the
  envelope; it can never be mistaken for a span-grounding digest.

* **evidence** — one runtime **assertion record** (plus any caller-supplied captures)::

      evidence_id    = "evidence:runtime:<idempotency-digest>"
      source_id      = the runtime source_id (all evidence binds to it, as the sink demands)
      locator        = "runtime:<slug(actor)>:<observed_at or '-'>"
      content_digest = RUNTIME_ASSERTION_DIGEST  (a fixed 'no grounded span' marker)

  This entry is not a grounding span — runtime facts are asserted-by-an-actor, not
  span-grounded. It records *who* asserted and *when* (actor + ``observed_at`` in the locator),
  and its ``content_digest`` is a constant runtime marker (the same for every runtime assertion,
  precisely because there are no span bytes to digest). The sink structurally requires a
  non-empty ``evidence[]`` and relations require ≥1 ``evidence_id``; this single record
  satisfies that honestly, without claiming grounding. ``observed_at`` is metadata: it is
  stamped into the locator and node/relation properties but is deliberately **not** part of the
  idempotency key (see below). Optional ``captures`` (an LLM answer, a web-search snippet) are
  attached here as *additional* evidence entries — recorded as provenance, not as grounding
  spans — rather than as first-class knowledge nodes (see :func:`append_fact`).

* **nd** — ``facet="nD"``, ``system_id="system:runtime-capture"``, ``axes=[dimension]`` (the
  single declared axis is the caller's ``dimension``), ``dimension_count=1``.

* **nodes** — ``node_type="entity"``; ``node_id="entity:<slug(term)>:<digest10(term)>"`` (the
  slug keeps it debuggable, the digest keeps distinct terms distinct and the same term
  stable/idempotent across appends). Every node carries ``properties.grounding="runtime"`` and
  the asserting ``properties.actor`` so a consumer can tell it apart from a span-grounded node.
  Each node also carries a **scalar** coordinate on the declared axis: for a fact triple the
  subject sits at the object value along that axis (``dimensions={dimension: object}``) — the
  fact *places* the subject at the object on the chosen dimension. The subject node's
  ``statement`` property carries the full canonical triple text so all three terms are
  searchable through ``search_similar`` (which derives a Doc's text from
  ``statement``/``bearer``/``action``).

* **relations** — ``relation_type=slug(predicate)`` (the raw predicate is kept in
  ``properties.predicate``, alongside ``properties.grounding="runtime"``); endpoints reference
  the entity node ids; ``dimension`` is the declared axis; ``evidence_ids`` list the runtime
  assertion record (and any captures).

* **idempotency_key** — ``"runtime-fact:<digest>"`` / ``"runtime-inference:<digest>"`` where
  the digest is over the canonical JSON of ``(triple|path, dimension, actor)``. Re-appending
  the *same* knowledge by the *same* actor is a no-op (receipt ``status="unchanged"``).
  ``observed_at`` is not in the key: the same fact is the same knowledge whenever observed. A
  caller who re-appends the same triple with a *different* explicit ``observed_at`` gets the
  sink's :class:`~versum.ingestion.subgraph.IdempotencyConflictError`, because that would
  silently rebind one key to different persisted content — the sink refuses that by design.

llm / web evidence
------------------
An LLM answer or a web-search capture is *support for* a fact, not an independently asserted
graph fact, so it is attached as an ``evidence[]`` entry (via the ``captures`` argument of
:func:`append_fact` / :func:`append_inference`) rather than promoted to a first-class node. A
capture's ``content_digest`` is the honest sha256 of the captured content — it hashes real
bytes and is recorded as provenance, not as a grounding span for the runtime assertion. This
keeps the knowledge plane (nodes/relations) clean while preserving provenance.

Everything here is stdlib + versum-internal.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .ingestion.subgraph import (
    SCHEMA,
    DimensionedSubgraph,
    DimensionedSubgraphSink,
    UpsertReceipt,
)

SYSTEM_ID = "system:runtime-capture"
NODE_TYPE = "entity"
#: The explicit provenance-class marker stamped on every runtime node and relation, so a
#: consumer can distinguish a runtime-asserted node from a span-grounded one.
RUNTIME_GROUNDING = "runtime"
#: Namespaces the runtime provenance markers; bumped only if their meaning changes.
_RUNTIME_PROVENANCE = "loomground.versum.runtime-provenance/v1"
_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def _marker_digest(*parts: str) -> str:
    """A sha256 over a fixed runtime *marker* string — never over asserted knowledge."""
    payload = ":".join((_RUNTIME_PROVENANCE, *parts))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


#: The synthetic runtime **assertion-record** digest — a fixed sentinel meaning "asserted at
#: runtime by an actor, with no grounded source span". It is identical for every runtime
#: assertion precisely because there are no span bytes to digest, and is never a hash of the
#: assertion. It exists only to satisfy the sink's ``evidence[].content_digest`` field.
RUNTIME_ASSERTION_DIGEST = _marker_digest("assertion")


class RuntimeCaptureError(ValueError):
    """A runtime capture argument cannot be lowered into a valid envelope."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _short(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()[:10]


def _slug(text: str) -> str:
    """A lowercase contract-identifier token: [a-z0-9._-], never empty."""
    slug = _SLUG_RE.sub("-", str(text).strip().lower()).strip("-._")
    return slug or "x"


def _term(text: str) -> str:
    """A term is a non-empty string; anything else is a capture error."""
    if not isinstance(text, str) or not text.strip():
        raise RuntimeCaptureError("terms (subject/predicate/object) must be non-empty strings")
    return text.strip()


def _axis(dimension: str) -> str:
    if not isinstance(dimension, str) or not dimension.strip():
        raise RuntimeCaptureError("dimension must be a non-empty axis identifier")
    return dimension.strip()


def _node_id(term: str) -> str:
    return f"{NODE_TYPE}:{_slug(term)}:{_short(term)}"


def _entity_node(term: str, *, axis: str, coordinate: str, statement: str, actor: str,
                 bearer: str = "", action: str = "", kind: str = "runtime-entity") -> dict:
    return {
        "node_id": _node_id(term),
        "node_type": NODE_TYPE,
        "dimensions": {axis: coordinate},
        "properties": {
            "name": term,
            "statement": statement,
            "bearer": bearer,
            "action": action,
            "kind": kind,
            # Explicit provenance class: this node is asserted at runtime, not span-grounded.
            "grounding": RUNTIME_GROUNDING,
            "actor": actor,
        },
    }


def _runtime_source(actor: str) -> dict:
    """The runtime source for ``actor``.

    ``content_digest`` is the *identity* of the runtime source (a hash of the source_id under
    the runtime marker), never a digest of the asserted knowledge — so it can never be mistaken
    for a span-grounding digest.
    """
    source_id = f"runtime:{_slug(actor)}"
    return {"source_id": source_id, "content_digest": _marker_digest("source", source_id)}


def _evidence_entries(actor: str, source_id: str, observed_at: str | None,
                      idempotency_seed: str, captures) -> tuple[list[dict], list[str]]:
    """The runtime **assertion record** entry plus any caller-supplied captures.

    Returns ``(entries, evidence_ids)``; every entry binds to ``source_id`` (the sink demands
    all evidence share the envelope source). The first entry is the runtime assertion record —
    NOT a grounding span: its ``content_digest`` is the fixed :data:`RUNTIME_ASSERTION_DIGEST`
    marker and its ``locator`` names the asserting actor and observation time. ``captures`` is
    an optional sequence of mappings ``{"kind": "llm_answer"|"websearch"|…, "content": str,
    "locator"?: str}`` recorded as provenance; a capture's ``content_digest`` honestly hashes
    its own content.
    """
    base_id = "evidence:runtime:" + _short([source_id, idempotency_seed])
    stamp = observed_at if observed_at not in (None, "") else "-"
    entries = [{
        "evidence_id": base_id,
        "source_id": source_id,
        "locator": f"runtime:{_slug(actor)}:{stamp}",
        "content_digest": RUNTIME_ASSERTION_DIGEST,
    }]
    evidence_ids = [base_id]
    for index, capture in enumerate(captures or ()):
        if not isinstance(capture, Mapping):
            raise RuntimeCaptureError("each capture must be a mapping")
        kind = _slug(str(capture.get("kind") or "capture"))
        content = capture.get("content", "")
        if not isinstance(content, str) or not content:
            raise RuntimeCaptureError("each capture must carry non-empty 'content'")
        cid = f"evidence:{kind}:{_short([content, index])}"
        locator = capture.get("locator")
        if not (isinstance(locator, str) and locator):
            locator = f"runtime:{kind}:{_slug(actor)}:{stamp}#{index}"
        entries.append({
            "evidence_id": cid,
            "source_id": source_id,
            "locator": locator,
            "content_digest": _digest(content),
        })
        evidence_ids.append(cid)
    return entries, evidence_ids


def _upsert(store_root: str | Path, envelope: dict) -> UpsertReceipt:
    """Validate the envelope, then write it through the canonical sink.

    ``store_root`` is authorized as its own root: runtime capture writes into exactly the
    store it is handed, the same containment the file-ingest sink enforces.
    """
    graph = DimensionedSubgraph.from_dict(envelope)
    sink = DimensionedSubgraphSink(store_root, authorized_store_root=store_root)
    return sink.upsert(graph)


def append_fact(store_root: str | Path, *, subject: str, predicate: str, object: str,
                dimension: str, actor: str, observed_at: str | None = None,
                captures: Sequence[Mapping[str, Any]] | None = None) -> UpsertReceipt:
    """Append a runtime **fact triple** (subject, predicate, object) on ``dimension``.

    Lowers the triple to a 2-node (subject entity, object entity) + 1-relation subgraph and
    writes it through the sink as an explicitly runtime-asserted (``grounding="runtime"``)
    provenance class. See the module docstring for the exact envelope conventions. Returns the
    sink :class:`~versum.ingestion.subgraph.UpsertReceipt` (``status`` is ``"inserted"`` the
    first time, ``"unchanged"`` on an identical re-append).

    ``captures`` optionally attaches LLM/web provenance as extra ``evidence`` entries.
    """
    subject = _term(subject)
    predicate = _term(predicate)
    object = _term(object)
    axis = _axis(dimension)
    if not isinstance(actor, str) or not actor.strip():
        raise RuntimeCaptureError("actor must be a non-empty string")

    triple_text = f"{subject} {predicate} {object}"
    knowledge = {"kind": "fact", "subject": subject, "predicate": predicate,
                 "object": object, "dimension": axis, "actor": actor}
    idempotency_key = "runtime-fact:" + _short(knowledge)

    source = _runtime_source(actor)
    evidence, evidence_ids = _evidence_entries(
        actor, source["source_id"], observed_at, idempotency_key, captures)

    subject_node = _entity_node(
        subject, axis=axis, coordinate=object, statement=triple_text, actor=actor,
        bearer=subject, action=object, kind="runtime-fact")
    object_node = _entity_node(
        object, axis=axis, coordinate=object, statement=object, actor=actor,
        kind="runtime-entity")
    # A self-referential triple (subject == object) collapses to a single node.
    nodes = [subject_node]
    if object_node["node_id"] != subject_node["node_id"]:
        nodes.append(object_node)

    stamp = observed_at if observed_at not in (None, "") else ""
    relation = {
        "relation_id": "rel:" + _short(knowledge),
        "relation_type": _slug(predicate),
        "source": {"kind": "node", "value": subject_node["node_id"]},
        "target": {"kind": "node", "value": object_node["node_id"]},
        "dimension": axis,
        "evidence_ids": evidence_ids,
        "properties": {"predicate": predicate, "actor": actor, "observed_at": stamp,
                       "grounding": RUNTIME_GROUNDING},
    }

    envelope = {
        "schema": SCHEMA,
        "idempotency_key": idempotency_key,
        "source": source,
        "evidence": evidence,
        "nd": {"facet": "nD", "system_id": SYSTEM_ID,
               "dimension_count": 1, "axes": [axis]},
        "nodes": nodes,
        "relations": [relation],
    }
    return _upsert(store_root, envelope)


def append_inference(store_root: str | Path, *, path: Sequence[Mapping[str, Any]],
                     dimension: str, actor: str, observed_at: str | None = None,
                     captures: Sequence[Mapping[str, Any]] | None = None) -> UpsertReceipt:
    """Append a runtime **inference** — a multi-hop path — on ``dimension``.

    ``path`` is a non-empty sequence of hops, each a mapping
    ``{"subject": str, "predicate": str, "object": str}``. Distinct terms across the path
    become entity nodes; each hop becomes one relation, yielding a node/relation chain written
    through the sink under the same runtime (``grounding="runtime"``) conventions as
    :func:`append_fact`. Returns the sink
    :class:`~versum.ingestion.subgraph.UpsertReceipt`.
    """
    axis = _axis(dimension)
    if not isinstance(actor, str) or not actor.strip():
        raise RuntimeCaptureError("actor must be a non-empty string")
    hops = list(path or ())
    if not hops:
        raise RuntimeCaptureError("path must carry at least one hop")

    normalized: list[dict] = []
    for hop in hops:
        if not isinstance(hop, Mapping):
            raise RuntimeCaptureError("each hop must be a mapping with subject/predicate/object")
        normalized.append({
            "subject": _term(hop.get("subject")),
            "predicate": _term(hop.get("predicate")),
            "object": _term(hop.get("object")),
        })

    knowledge = {"kind": "inference", "path": normalized, "dimension": axis, "actor": actor}
    knowledge_digest = _digest(knowledge)
    idempotency_key = "runtime-inference:" + _short(knowledge)

    source = _runtime_source(actor)
    evidence, evidence_ids = _evidence_entries(
        actor, source["source_id"], observed_at, idempotency_key, captures)

    path_text = " ".join(
        f"{h['subject']} {h['predicate']} {h['object']}" for h in normalized)
    nodes: dict[str, dict] = {}

    def _remember(term: str, statement: str) -> str:
        node = _entity_node(term, axis=axis, coordinate=term, statement=statement,
                            actor=actor, bearer=term, kind="runtime-inference")
        nodes.setdefault(node["node_id"], node)
        return node["node_id"]

    stamp = observed_at if observed_at not in (None, "") else ""
    relations: list[dict] = []
    for index, hop in enumerate(normalized):
        # The first subject carries the whole inference text so the path is searchable.
        subj_statement = path_text if index == 0 else hop["subject"]
        subject_id = _remember(hop["subject"], subj_statement)
        object_id = _remember(hop["object"], hop["object"])
        relations.append({
            "relation_id": "rel:" + _short([knowledge_digest, index]),
            "relation_type": _slug(hop["predicate"]),
            "source": {"kind": "node", "value": subject_id},
            "target": {"kind": "node", "value": object_id},
            "dimension": axis,
            "evidence_ids": evidence_ids,
            "properties": {"predicate": hop["predicate"], "actor": actor,
                           "observed_at": stamp, "hop": index,
                           "grounding": RUNTIME_GROUNDING},
        })

    envelope = {
        "schema": SCHEMA,
        "idempotency_key": idempotency_key,
        "source": source,
        "evidence": evidence,
        "nd": {"facet": "nD", "system_id": SYSTEM_ID,
               "dimension_count": 1, "axes": [axis]},
        "nodes": list(nodes.values()),
        "relations": relations,
    }
    return _upsert(store_root, envelope)


def fact_node_ids(*, subject: str, object: str) -> tuple[str, str]:
    """The (subject, object) node ids :func:`append_fact` mints — for callers that need to
    address a runtime node afterwards (e.g. erasure via the ``"sink:"`` convention)."""
    return _node_id(_term(subject)), _node_id(_term(object))
