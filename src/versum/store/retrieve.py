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
from dataclasses import dataclass, field
from pathlib import Path

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# facet fields carried on a Doc (structured axes; no domain value named here)
FACET_FIELDS = ("type", "polarity", "predicate", "modality", "quantification",
                "dimension", "domain", "library", "concept_id", "m")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens of length ≥ 2 (language-neutral)."""
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= 2]


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
             "domain": d.domain, "library": d.library, "concept_id": d.concept_id}
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


# ── KG loader ─────────────────────────────────────────────────────
def _read_csv(path: Path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader((line.replace("\x00", "") for line in fh)))


def docs_from_kg(kg_root, include_claims: bool = True, include_concepts: bool = True) -> list:
    """Build the Doc set from a materialized KG: claim rows (by-domain/*/claims.csv) and canon
    concepts (canon.json). Domain comes from the folder; facets are carried from the rows."""
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
    return docs


def from_kg(kg_root, dense: Dense | None = None, **kw) -> SearchIndex:
    return SearchIndex(docs_from_kg(kg_root, **kw), dense=dense)
