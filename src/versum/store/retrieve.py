"""versum/retrieve.py — hybrid matching / retrieval over the materialized KG (ADR-004).

The coordinate fingerprint is not a search index; this is. Three layers:

  * **facets** — exact-match postings on the structured axes (type, polarity, predicate,
    modality, quantification, domain, library, concept_id, depth ``m``).
  * **sparse** — Okapi BM25 over text (claim text, concept label + surface term). Pure python,
    deterministic, no dependency.
  * **dense** — an *injected* adapter (``Dense.embed``). The real one is device-side and
    model-agnostic (the user's Qwen/Phi via Ollama); it is never called from core. ``NullDense``
    (default) skips reranking; ``HashingDense`` is a deterministic fallback for tests.

A query filters by facets, ranks the survivors by BM25, and optionally re-ranks by dense
similarity (score fusion). Domain-neutral: this module names no domain value — facets and text
are carried through from the KG rows. Deterministic given a fixed corpus and (optional) embedder.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# facet fields carried on a Doc (structured axes; no domain value named here)
FACET_FIELDS = ("type", "polarity", "predicate", "modality", "quantification",
                "dimension", "domain", "library", "concept_id", "m")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens of length ≥ 2 (language-neutral)."""
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= 2]


def _tokens_of(value) -> set:
    """Token set for a single facet value — a string/number, or a list of them."""
    if isinstance(value, (list, tuple, set)):
        out: set = set()
        for item in value:
            out |= _tokens_of(item)
        return out
    if value in (None, ""):
        return set()
    return set(tokenize(str(value)))


def query_tokens(query) -> set:
    """Token bag for a keyword-overlap query.

    ``query`` is a plain string (taken as the summary) or a mapping carrying a
    ``summary`` and ``keywords``/``facets`` (each a list of terms, or a mapping whose
    values are strings or lists). Tokenisation matches :func:`tokenize` throughout.
    """
    if isinstance(query, str):
        return set(tokenize(query))
    if isinstance(query, Mapping):
        toks = set(tokenize(str(query.get("summary", ""))))
        for key in ("keywords", "facets"):
            raw = query.get(key)
            if isinstance(raw, Mapping):
                for v in raw.values():
                    toks |= _tokens_of(v)
            elif raw is not None:
                toks |= _tokens_of(raw)
        return toks
    return set()


def _doc_tokens(doc: "Doc") -> set:
    """Token bag for a Doc: its text plus all of its facet values."""
    toks = set(tokenize(doc.text))
    for v in doc.facets.values():
        toks |= _tokens_of(v)
    return toks


@dataclass
class Doc:
    doc_id: str
    type: str                       # "claim" | "concept" | "composite"
    text: str = ""
    facets: dict = field(default_factory=dict)
    canonical_urn: str = ""
    domain: str = ""
    library: str = ""
    concept_id: str = ""
    #: A monotone recency signal (higher ⇒ more recent) used only to break ties in
    #: keyword-overlap search. The store carries no wall-clock on claim rows, so it
    #: defaults to 0.0; consumers that track recency may stamp it when building Docs.
    recency: float = 0.0


# ── sparse: Okapi BM25 ────────────────────────────────────────────
class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.N = 0
        self.avgdl = 0.0
        self.doc_len: list[int] = []
        self.tf: list[dict] = []
        self.idf: dict = {}

    def fit(self, doc_tokens: list[list[str]]) -> "BM25":
        self.N = len(doc_tokens)
        self.doc_len = [len(t) for t in doc_tokens]
        self.avgdl = (sum(self.doc_len) / self.N) if self.N else 0.0
        df: dict = {}
        self.tf = []
        for toks in doc_tokens:
            d: dict = {}
            for t in toks:
                d[t] = d.get(t, 0) + 1
            self.tf.append(d)
            for t in d:
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log(1 + (self.N - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        return self

    def score(self, q_tokens, i: int) -> float:
        if not self.avgdl:
            return 0.0
        dl = self.doc_len[i]
        s = 0.0
        tfi = self.tf[i]
        for t in q_tokens:
            f = tfi.get(t)
            if not f:
                continue
            s += self.idf.get(t, 0.0) * (f * (self.k1 + 1)) / (
                f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s


# ── dense adapter contract (device-side, model-agnostic) ──────────
class Dense:
    """Interface for a semantic embedder. Implemented on the device (Ollama Qwen/Phi, …);
    never called from core. ``embed(texts) -> list[vector] | None`` (None ⇒ no rerank)."""
    def embed(self, texts):  # pragma: no cover - interface
        raise NotImplementedError


class NullDense(Dense):
    """Default: no embeddings, no rerank."""
    def embed(self, texts):
        return None


class HashingDense(Dense):
    """Deterministic feature-hashing embedder — NOT semantic, only exercises the rerank path in
    tests without a model. The real device adapter replaces this."""
    def __init__(self, dim: int = 64):
        self.dim = dim

    def embed(self, texts):
        import hashlib
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for tok in tokenize(t):
                h = int(hashlib.sha1(tok.encode()).hexdigest(), 16)  # stable across processes
                v[h % self.dim] += 1.0
            out.append(v)
        return out


def _cosine(a, b) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return num / (na * nb)


# ── the index ─────────────────────────────────────────────────────
class SearchIndex:
    def __init__(self, docs: list[Doc], dense: Dense | None = None):
        self.docs = docs
        self.dense = dense or NullDense()
        self._rebuild()

    def _rebuild(self):
        self._postings: dict = {}          # (field, value) -> set(idx)
        for i, d in enumerate(self.docs):
            for fld in FACET_FIELDS:
                val = d.facets.get(fld, "")
                if val != "" and val is not None:
                    self._postings.setdefault((fld, str(val)), set()).add(i)
        self.bm25 = BM25().fit([tokenize(d.text) for d in self.docs])
        self._emb = None                    # lazy dense doc embeddings

    def update(self, docs=(), remove_ids=()) -> dict:
        """Incrementally upsert/remove documents, then refresh corpus-wide ranking statistics."""
        current = {d.doc_id: d for d in self.docs}
        removed = sum(1 for doc_id in remove_ids if current.pop(doc_id, None) is not None)
        added = replaced = 0
        for doc in docs:
            if doc.doc_id in current:
                replaced += 1
            else:
                added += 1
            current[doc.doc_id] = doc
        self.docs = [current[k] for k in sorted(current)]
        self._rebuild()
        return {"added": added, "replaced": replaced, "removed": removed,
                "total": len(self.docs)}

    def save(self, path) -> None:
        """Persist the portable document snapshot; derived postings/BM25 rebuild on load."""
        payload = {"format": "versum.search-index/v1", "docs": [
            {"doc_id": d.doc_id, "type": d.type, "text": d.text,
             "facets": d.facets, "canonical_urn": d.canonical_urn,
             "domain": d.domain, "library": d.library, "concept_id": d.concept_id,
             "recency": d.recency}
            for d in self.docs]}
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path, dense: Dense | None = None) -> "SearchIndex":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("format") != "versum.search-index/v1":
            raise ValueError("incompatible persisted search-index format")
        return cls([Doc(**d) for d in payload.get("docs", [])], dense=dense)

    def _candidates(self, filters: dict) -> set:
        if not filters:
            return set(range(len(self.docs)))
        sets = []
        for fld, val in filters.items():
            sets.append(self._postings.get((fld, str(val)), set()))
        return set.intersection(*sets) if sets else set()

    def _doc_embeddings(self):
        if self._emb is None:
            self._emb = self.dense.embed([d.text for d in self.docs])
        return self._emb

    def search(self, query: str = "", filters: dict | None = None, k: int = 10,
               alpha: float = 0.6) -> list[dict]:
        """Facet-filter, then rank. With a query: BM25 (fused with dense rerank when an embedder
        is set, weight ``alpha`` on BM25). Without a query: facet matches, stable by doc_id.
        Returns up to ``k`` hits with score + provenance."""
        cand = self._candidates(filters or {})
        q_tokens = tokenize(query)
        scored = []
        if q_tokens:
            raw = {i: self.bm25.score(q_tokens, i) for i in cand}
            hi = max(raw.values()) if raw else 0.0
            dense_vecs = self._doc_embeddings() if not isinstance(self.dense, NullDense) else None
            q_vec = self.dense.embed([query])[0] if dense_vecs is not None else None
            for i in cand:
                bm = (raw[i] / hi) if hi else 0.0
                if q_vec is not None and dense_vecs is not None:
                    ds = _cosine(q_vec, dense_vecs[i])
                    score = alpha * bm + (1 - alpha) * ds
                else:
                    score = bm
                if score > 0:
                    scored.append((score, i))
        else:
            scored = [(1.0, i) for i in cand]
        scored.sort(key=lambda si: (-si[0], self.docs[si[1]].doc_id))
        out = []
        for score, i in scored[:k]:
            d = self.docs[i]
            out.append({"doc_id": d.doc_id, "type": d.type, "score": round(score, 6),
                        "canonical_urn": d.canonical_urn, "domain": d.domain,
                        "library": d.library, "concept_id": d.concept_id,
                        "snippet": d.text[:200]})
        return out

    def search_similar(self, query, k: int = 10, filters: dict | None = None) -> list[dict]:
        """Keyword-overlap (Jaccard) similarity search over claims/concepts.

        A deterministic, dependency-free companion to :meth:`search` that ports the
        keyword-overlap ranking of an upstream workspace memory into Versum. ``query`` is
        a plain string (taken as the summary) or a mapping carrying a ``summary`` and
        ``keywords``/``facets`` (see :func:`query_tokens`). Each candidate's token bag is
        its text plus its facet values (:func:`_doc_tokens`); survivors are ranked by the
        Jaccard similarity of the two bags, dropping zero-overlap docs. Ties are broken by
        recency (higher :attr:`Doc.recency` first), then ``doc_id`` for a stable order.
        ``filters`` scope the candidates exactly as :meth:`search`. Returns up to ``k``
        hits in the same shape as :meth:`search`.
        """
        q_tokens = query_tokens(query)
        cand = self._candidates(filters or {})
        scored = []
        if q_tokens:
            for i in cand:
                d_tokens = _doc_tokens(self.docs[i])
                union = q_tokens | d_tokens
                if not union:
                    continue
                sim = len(q_tokens & d_tokens) / len(union)
                if sim > 0:
                    scored.append((sim, i))
        scored.sort(key=lambda si: (-si[0], -self.docs[si[1]].recency, self.docs[si[1]].doc_id))
        out = []
        for score, i in scored[:k]:
            d = self.docs[i]
            out.append({"doc_id": d.doc_id, "type": d.type, "score": round(score, 6),
                        "canonical_urn": d.canonical_urn, "domain": d.domain,
                        "library": d.library, "concept_id": d.concept_id,
                        "snippet": d.text[:200]})
        return out


# ── KG loader ─────────────────────────────────────────────────────
def _read_csv(path: Path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader((line.replace("\x00", "") for line in fh)))


def docs_from_kg(kg_root, include_claims: bool = True, include_concepts: bool = True,
                 *, exclude_erased: bool = True) -> list:
    """Build the Doc set from a materialized KG: claim rows (by-domain/*/claims.csv) and canon
    concepts (canon.json). Domain comes from the folder; facets are carried from the rows.

    ``exclude_erased`` (default) drops every node the erasure projection tombstones — both
    logically deleted and purged claims/concepts/sources (see :mod:`versum.store.erasure`) —
    so no read (``search`` / ``search_similar``) ever surfaces an erased item.
    """
    kg_root = Path(kg_root).expanduser()
    bd = kg_root / "by-domain"
    root = bd if bd.is_dir() else kg_root
    docs: list = []
    if include_claims:
        for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
            for r in _read_csv(d / "claims.csv"):
                iid = (r.get("item_id") or "").strip()
                if not iid:
                    continue
                docs.append(Doc(
                    doc_id=f"claim:{iid}", type="claim", text=r.get("text", ""),
                    canonical_urn=(r.get("canonical_urn") or "").strip(),
                    domain=d.name, library=(r.get("library") or "").strip(),
                    facets={"type": "claim", "polarity": r.get("polarity", ""),
                            "predicate": r.get("predicate", ""),
                            "dimension": r.get("dimension", ""),
                            "modality": r.get("modality", ""),
                            "quantification": r.get("quantification", ""),
                            "domain": d.name, "library": (r.get("library") or "").strip()}))
    if include_concepts:
        cj = kg_root / "canon.json"
        if cj.exists():
            canon = json.loads(cj.read_text(encoding="utf-8"))
            for c in canon.get("concepts", []):
                cid = c.get("concept_id", "")
                text = " ".join(str(c.get(k, "")) for k in
                                ("label", "surface_key_term", "key_term", "predicate", "example"))
                doms = c.get("domains", []) or [""]
                docs.append(Doc(
                    doc_id=f"concept:{cid}", type="concept", text=text, concept_id=cid,
                    domain=doms[0] if doms else "",
                    facets={"type": "concept", "concept_id": cid,
                            "predicate": c.get("predicate", ""),
                            "dimension": c.get("dimension", ""),
                            "polarity": c.get("polarity", ""),
                            "m": c.get("m", 1)}))
    if exclude_erased:
        from .erasure import load_tombstones  # stdlib-only reader; no write machinery
        tombs = load_tombstones(kg_root)
        docs = [d for d in docs if not tombs.hides(d.doc_id, d.canonical_urn)]
    return docs


def from_kg(kg_root, dense: Dense | None = None, **kw) -> SearchIndex:
    return SearchIndex(docs_from_kg(kg_root, **kw), dense=dense)


# ── dimensioned-subgraph loader ───────────────────────────────────
#: Controlled node fields carried through as Doc facets (the human-meaningful text —
#: statement/bearer/action — goes into Doc.text, not here).
_ND_FACET_FIELDS = ("operator", "bearer", "incident", "condition",
                    "exception", "deadline", "sanction")


def _node_field(node: Mapping, props: Mapping, name: str):
    """Read a logical node field: top-level first (raw ingester node), else properties
    (the persisted envelope shape, where the deontic fields live under ``properties``)."""
    if name in node:
        return node[name]
    return props.get(name, "")


def docs_from_dimensioned_store(store_root, *, exclude_erased: bool = True) -> list:
    """Build the Doc set from the canonical DimensionedSubgraphSink store.

    Reads every signed transaction under ``<store_root>/_dimensioned_subgraph_transactions``
    (via :func:`versum.ingestion.subgraph.load_dimensioned_subgraphs`) and emits one Doc per
    subgraph NODE, so sink-ingested content is searchable through the same ``search_similar``
    ranking as the overlay/claims store. The persisted envelope node is
    ``{node_id, node_type, dimensions, properties}``; the deontic ingester's logical fields
    (``statement``, ``operator``, ``bearer``, ``action``, …) live under ``properties`` — this
    reader tolerates either shape.

    ``exclude_erased`` (default) drops every sink node the erasure projection tombstones —
    both logically deleted and purged nodes/sources (see :mod:`versum.store.erasure`) — so no
    sink read ever surfaces an erased item. The tombstone set is keyed by the raw ``node_id``
    (== ``Doc.doc_id``) and the subgraph ``source.source_id`` (== ``Doc.canonical_urn``).
    """
    from ..ingestion.subgraph import load_dimensioned_subgraphs  # avoid an import cycle
    docs: list = []
    for graph in load_dimensioned_subgraphs(store_root):
        source = graph.get("source") if isinstance(graph, Mapping) else None
        canonical_urn = ""
        if isinstance(source, Mapping):
            canonical_urn = str(source.get("source_id") or "")
        for node in graph.get("nodes", []):
            if not isinstance(node, Mapping):
                continue
            props = node.get("properties") if isinstance(node.get("properties"), Mapping) else {}
            doc_id = node.get("node_id") or node.get("id")
            if not doc_id:
                continue
            node_type = (node.get("node_type") or node.get("kind")
                         or props.get("kind") or "norm")
            text = " ".join(
                str(v) for v in (
                    _node_field(node, props, "statement"),
                    _node_field(node, props, "bearer"),
                    _node_field(node, props, "action"),
                ) if v not in (None, "")
            )
            facets: dict = {}
            for fld in _ND_FACET_FIELDS:
                val = _node_field(node, props, fld)
                if val not in (None, "", [], {}):
                    facets[fld] = val
            docs.append(Doc(
                doc_id=str(doc_id), type=str(node_type), text=text,
                facets=facets, canonical_urn=canonical_urn))
    if exclude_erased:
        from .erasure import load_tombstones  # stdlib-only reader; no write machinery
        tombs = load_tombstones(store_root)
        docs = [d for d in docs if not tombs.hides(d.doc_id, d.canonical_urn)]
    return docs


def from_dimensioned_store(store_root, dense: Dense | None = None, *,
                           exclude_erased: bool = True) -> SearchIndex:
    """SearchIndex over the DimensionedSubgraphSink store (one Doc per subgraph node).

    Companion to :func:`from_kg` for the *other* persistence representation: the signed
    transactions written by :class:`versum.ingestion.subgraph.DimensionedSubgraphSink`.
    ``search_similar`` works over the returned index unchanged. ``exclude_erased`` (default)
    hides tombstoned sink nodes/sources (see :mod:`versum.store.erasure`).
    """
    return SearchIndex(
        docs_from_dimensioned_store(store_root, exclude_erased=exclude_erased), dense=dense)


# ── full-record retrieval over the dimensioned-subgraph store ─────
# ``search_similar`` / ``from_dimensioned_store`` return *lossy* hits — ``doc_id``, ``score``
# and a text ``snippet[:200]`` — enough to rank, not enough to reconstruct a knowledge item.
# A consumer that is retiring its own parallel store (RVND) must read the WHOLE record back:
# the node itself (``node_type`` + ``dimensions`` + all ``properties``), every relation that
# touches it (in *both* directions), and the transaction's ``source`` / ``evidence``
# provenance — so it can rebuild a knowledge "pair" and apply its OWN enforcement over it
# (redaction, lock/seal, source scoping). Versum owns storage + retrieval and returns the
# full record; it does NOT apply redaction or lock/seal — those stay in the consumer.
#
# The record shape (a plain JSON-able dict; :func:`search_records` adds a ``"score"``)::
#
#     {"node_id", "node_type", "dimensions", "properties",
#      "source": {"source_id", "content_digest"},   # the transaction's source
#      "evidence": [ … ],                            # the transaction's evidence[]
#      "relations": [ … ]}                           # every relation touching the node
def _relation_touches_node(relation: Mapping, node_id: str) -> bool:
    """True when a relation references ``node_id`` on a ``kind == "node"`` endpoint
    (either the ``source`` or the ``target`` end — i.e. relations in both directions)."""
    for endpoint_name in ("source", "target"):
        endpoint = relation.get(endpoint_name)
        if isinstance(endpoint, Mapping) and endpoint.get("kind") == "node":
            if str(endpoint.get("value")) == node_id:
                return True
    return False


def _full_record(graph: Mapping, node: Mapping, canonical_urn: str) -> dict:
    """Assemble the full record for one subgraph ``node`` within its transaction ``graph``.

    ``source`` / ``evidence`` are the transaction's provenance; ``relations`` is every
    relation in the transaction that touches this node in either direction.
    """
    node_id = str(node.get("node_id") or node.get("id"))
    props = node.get("properties")
    dims = node.get("dimensions")
    node_type = (node.get("node_type") or node.get("kind")
                 or (props.get("kind") if isinstance(props, Mapping) else None) or "norm")
    source = graph.get("source")
    return {
        "node_id": node_id,
        "node_type": str(node_type),
        "dimensions": dict(dims) if isinstance(dims, Mapping) else {},
        "properties": dict(props) if isinstance(props, Mapping) else {},
        "source": dict(source) if isinstance(source, Mapping) else {},
        "evidence": [dict(e) for e in graph.get("evidence", []) if isinstance(e, Mapping)],
        "relations": [dict(r) for r in graph.get("relations", [])
                      if isinstance(r, Mapping) and _relation_touches_node(r, node_id)],
    }


def _iter_node_records(store_root):
    """Yield ``(node_id, canonical_urn, record)`` for every node in every signed transaction.

    No erasure filtering here — callers apply their own tombstone policy. ``canonical_urn`` is
    the subgraph ``source.source_id`` (the same key erasure tombstones a source under).
    """
    from ..ingestion.subgraph import load_dimensioned_subgraphs  # avoid an import cycle
    for graph in load_dimensioned_subgraphs(store_root):
        if not isinstance(graph, Mapping):
            continue
        source = graph.get("source")
        canonical_urn = str(source.get("source_id") or "") if isinstance(source, Mapping) else ""
        for node in graph.get("nodes", []):
            if not isinstance(node, Mapping):
                continue
            node_id = node.get("node_id") or node.get("id")
            if not node_id:
                continue
            yield str(node_id), canonical_urn, _full_record(graph, node, canonical_urn)


def get_record(store_root, node_id) -> dict | None:
    """The FULL record for one dimensioned-subgraph node, or ``None`` if absent/erased.

    Returns ``{node_id, node_type, dimensions, properties, source, evidence, relations}``
    where ``relations`` is every relation touching the node (both directions) and
    ``source`` / ``evidence`` are the transaction's provenance. This is the by-id, full-fidelity
    companion to the lossy ``search_similar`` hit: enough for a consumer to rebuild a knowledge
    item and apply its own enforcement (redaction, lock/seal, source scoping), which Versum
    does NOT apply here.

    Honours the WS-B erasure projection (:mod:`versum.store.erasure`): a logically deleted or
    purged node — or a node whose source is tombstoned — returns ``None``, exactly as it is
    hidden from every read. An unknown ``node_id`` also returns ``None``.
    """
    from .erasure import load_tombstones  # stdlib-only reader; no write machinery
    tombs = load_tombstones(store_root)
    for nid, canonical_urn, record in _iter_node_records(store_root):
        if nid == str(node_id):
            if tombs.hides(nid, canonical_urn):
                return None
            return record
    return None


def search_records(store_root, query, *, k: int = 10, filters: dict | None = None,
                   exclude_erased: bool = True) -> list[dict]:
    """Rank like :meth:`SearchIndex.search_similar`, but carry the FULL record per hit.

    Reuses the exact keyword-overlap ranking of ``from_dimensioned_store(...).search_similar``;
    each hit is the full :func:`get_record` record for the matched node plus its ``"score"`` —
    not a ``snippet``. ``k`` / ``filters`` behave as in ``search_similar``. ``exclude_erased``
    (default) hides tombstoned nodes/sources from both the ranking and the attached records.
    Versum returns the whole record; redaction and lock/seal remain the consumer's job.
    """
    index = from_dimensioned_store(store_root, exclude_erased=exclude_erased)
    hits = index.search_similar(query, k=k, filters=filters)
    if not hits:
        return []
    from .erasure import load_tombstones  # stdlib-only reader; no write machinery
    tombs = load_tombstones(store_root) if exclude_erased else None
    records: dict[str, dict] = {}
    for nid, canonical_urn, record in _iter_node_records(store_root):
        if tombs is not None and tombs.hides(nid, canonical_urn):
            continue
        records.setdefault(nid, record)
    out: list[dict] = []
    for hit in hits:
        record = records.get(hit["doc_id"])
        if record is None:
            continue
        out.append({**record, "score": hit["score"]})
    return out
