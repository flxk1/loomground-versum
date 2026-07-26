"""versum/canon.py — coordinate-identity curation: the mental-model / concept layer.

Every claim already carries a 5D+nD signature (the closed axes the extractor stamps:
polarity, predicate, modality, quantification) plus its grounding text. This module turns
that signature into a *content-derived coordinate* — a claim's mental-model identity. Two
claims from different sources that share a coordinate name the SAME concept, so the concept
layer EMERGES by convergence instead of being hand-authored, and a concept_id is a function
of a claim's content, never of its source.

Domain-neutral: the engine names no domain value. Predicate values, key terms and domain
labels are all DATA carried through from the claim rows and the folder layout — this module
hardcodes only language-generic function words for label hygiene.

  * ``coordinate_for(claim)`` — the claim's coordinate: the closed-axis signature plus a
    ``key_term`` parsed from the grounding text (a quoted term, else a salient capitalized
    phrase, else the most salient content token). Deterministic, no model, no network.
  * ``coordinate_id(coord)`` — a bare-slug ``concept_id`` (own identity, never a urn), a
    projection of the coordinate onto the IDENTITY axes (default polarity + predicate +
    key_term). A coarser identity than the full signature lets equivalent operators
    converge while the full signature is still recorded on the concept.
  * ``build_canon(claims, m_max=1)`` — the domain canon: concepts (one per coordinate, with
    support = how many claims / how many distinct sources / which domains), grounds edges
    (claim → concept), per-source fingerprints (a document's set of coordinate ids), and a
    convergence curve (distinct coordinates vs sources processed — it flattens toward the
    domain's canon ceiling as new sources stop minting new coordinates).

``m_max`` is the composition depth. At ``m_max=1`` a coordinate is a single claim's
signature (depth-1); deeper composition (co-occurring coordinates within a source forming
higher-order models) is a documented extension point, not yet minted.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import morph

# ── key-term extraction (language-generic; no domain vocabulary) ──────────────
_OPEN = "‘'\"“„«‹"
_CLOSE = "’'\"”“»›"
_QUOTED_RE = re.compile("[" + _OPEN + r"]([^" + _CLOSE + r"]{2,60})[" + _CLOSE + "]")
_CAP_RE = re.compile(r"\b([^\W\d_][\w-]*(?:\s+[A-ZÄÖÜ][\w-]*){1,3})")
_TOKEN_RE = re.compile(r"[^\W\d_]{4,}", re.UNICODE)

# Function words are LANGUAGE structure, not a domain. Kept minimal, multilingual, and free
# of any operator vocabulary so no domain marker can leak in via a stopword list.
_FUNCTION_WORDS = frozenset("""
the a an and or of to for in on at by with from as into onto per via at within without
is are was were be been being this that these those it its their our your his her
they them we you which who what when where whether while if then so than but not no nor
each any all both other more most such same only also may can could would should
der die das den dem des ein eine einer eines einem und oder fuer mit aus bei auch
kein keine ist sind war waren wird werden dieser diese dieses nicht durch nach ueber
unter im am zum zur vom von beim als um bis dass wenn sowie bzw dabei damit deren dessen
seine seiner ihre ihrer wie wo wobei sich nur noch schon
le la les un une des du et ou pour dans par sur avec que se qui ne pas
el los las una para con del por como que su se
""".split())


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:48]


# A candidate whose slug carries a single hyphen-free run this long is almost always a
# spacing-artifact glob (a PDF text layer that dropped spaces), not a real term — reject it.
_GLOB_RUN = 34


def _is_glob(slug: str) -> bool:
    return any(len(part) > _GLOB_RUN for part in slug.split("-"))


def _strip_edge_function_words(phrase: str) -> str:
    """Drop leading/trailing function words from a candidate phrase (sentence-initial
    capitalization and trailing connectives add noise to a key term)."""
    words = [w for w in re.split(r"\s+", phrase.strip()) if w]
    while words and words[0].lower() in _FUNCTION_WORDS:
        words.pop(0)
    while words and words[-1].lower() in _FUNCTION_WORDS:
        words.pop()
    return " ".join(words)


def key_term(text: str, marker: str = "") -> str:
    """The salient subject term of a claim's grounding text, as a slug (or "").

    Deterministic precedence, most-specific first: (1) a quoted term, (2) a multi-word
    capitalized phrase (edge function words stripped), (3) the most salient content token
    (longest, ties broken lexicographically for determinism). Language-generic — no domain
    value is named or preferred.
    """
    if not text:
        return ""
    m = _QUOTED_RE.search(text)
    if m:
        t = _slug(_strip_edge_function_words(m.group(1)))
        if t and t not in _FUNCTION_WORDS:
            return t
    caps = []
    for c in _CAP_RE.findall(text):
        c = _strip_edge_function_words(c)
        if c and " " in c:                       # keep multi-word phrases only
            caps.append(c)
    if caps:
        best = max(caps, key=lambda c: (len(c), c))
        s = _slug(best)
        if s and s not in _FUNCTION_WORDS:
            return s
    toks = [t for t in _TOKEN_RE.findall(text.lower()) if t not in _FUNCTION_WORDS]
    if toks:
        return _slug(sorted(toks, key=lambda w: (-len(w), w))[0])
    return ""


def candidate_terms(text: str) -> list[tuple]:
    """Every reasonable subject-term candidate in a claim's text, as ``(slug, is_quoted)``.

    Quoted terms (a strong, author-marked signal) and multi-word capitalized phrases (edge
    function words stripped). This is the *generator*; corpus salience (below) decides which
    candidates are allowed to name a concept, so one-off author names and OCR garble — which
    are never quoted and never recur across sources — are filtered out rather than clustered.
    """
    out, seen = [], set()
    for m in _QUOTED_RE.finditer(text or ""):
        s = _slug(_strip_edge_function_words(m.group(1)))
        if s and s not in _FUNCTION_WORDS and s not in seen and not _is_glob(s):
            seen.add(s); out.append((s, True))
    for c in _CAP_RE.findall(text or ""):
        c = _strip_edge_function_words(c)
        if c and " " in c:
            s = _slug(c)
            if s and s not in _FUNCTION_WORDS and s not in seen and not _is_glob(s):
                seen.add(s); out.append((s, False))
    return out


# ── coordinate identity ───────────────────────────────────────────────────────
IDENTITY_AXES = ("polarity", "predicate", "key_term")


def coordinate_for(claim: dict, m_max: int = 1, key_term_value=None) -> dict:
    """The full 5D+nD signature of a claim plus its ``key_term`` — its coordinate.

    ``m_max`` is the composition depth; at 1 the coordinate is this single claim's
    signature. Closed axes are read from the claim row (never inferred), polarity defaults
    to ``D`` (an is-claim) when absent. ``key_term_value`` lets a corpus-salience pass supply
    the key term (see :func:`build_canon`); when ``None`` the per-claim heuristic is used.
    """
    kt = key_term(claim.get("text", ""), claim.get("marker", "")) \
        if key_term_value is None else key_term_value
    return {
        "dimension": (claim.get("dimension") or "relational").strip(),
        "polarity": (claim.get("polarity") or "").strip() or "D",
        "predicate": (claim.get("predicate") or "").strip(),
        "modality": (claim.get("modality") or "").strip(),
        "quantification": (claim.get("quantification") or "").strip(),
        "key_term": kt,
        "m": 1,
    }


def coordinate_id(coord: dict, axes=IDENTITY_AXES) -> str:
    """A bare-slug ``concept_id`` = the coordinate projected onto the identity ``axes``.

    Always begins with ``m-`` (a mental-model id owning its identity, never a source urn)
    and matches ``^[a-z][a-z0-9-]*$``.
    """
    parts = []
    for a in axes:
        v = coord.get(a, "")
        parts.append(v if a == "key_term" else _slug(str(v)))
    tail = "-".join(p for p in parts if p)
    return "m-" + tail if tail else "m-x"


def _dominant(counter: dict) -> str:
    """The most frequent key in a count map (ties broken lexicographically)."""
    if not counter:
        return ""
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _label(coord: dict) -> str:  # human-readable concept label
    kt = (coord.get("key_term") or "").replace("-", " ").strip()
    pred = (coord.get("predicate") or "").strip()
    pol = "is" if (coord.get("polarity") or "D").upper() == "D" else "ought"
    head = kt or "(unnamed)"
    return f"{head} — {pred} ({pol})" if pred else f"{head} ({pol})"


def _edge_id(src_id: str, dst_id: str) -> str:
    return "grd-" + hashlib.sha1(f"{src_id}->{dst_id}".encode()).hexdigest()[:12]


def _source_key(claim: dict) -> str:
    return (claim.get("canonical_urn") or claim.get("source_urn") or "").strip()


def _salient_terms(per_source: dict, min_df: int) -> tuple:
    """Two things from the claim corpus: ``claim_cands`` (item_id → its candidate slugs, most
    specific first) and ``canonical`` (the set of slugs allowed to name a concept).

    A candidate is *canonical* iff it is quoted anywhere OR appears across at least ``min_df``
    distinct sources. This is corpus-derived salience — it names no domain value — and it is
    what filters one-off author names / OCR garble (never quoted, never recurring) out of the
    concept vocabulary so real, shared subjects converge instead of scattering.
    """
    df: dict[str, set] = {}
    quoted: set[str] = set()
    claim_cands: dict[str, list] = {}
    for s, s_claims in per_source.items():
        for c in s_claims:
            cands = candidate_terms(c.get("text", ""))
            iid = (c.get("item_id") or "").strip()
            claim_cands[iid] = [t for t, _q in cands]
            for t, is_q in cands:
                df.setdefault(t, set()).add(s)
                if is_q:
                    quoted.add(t)
    canonical = {t for t in df if t in quoted or len(df[t]) >= min_df}
    return claim_cands, canonical


def _pick_key_term(item_id: str, claim_cands: dict, canonical: set) -> str:
    """The claim's longest own candidate that is corpus-canonical (ties lexicographic), else
    "" — an axes-only coordinate rather than a guessed, noisy subject."""
    allowed = [t for t in claim_cands.get(item_id, ()) if t in canonical]
    if not allowed:
        return ""
    return sorted(allowed, key=lambda w: (-len(w), w))[0]


def _norm_key_term(surface: str, morph_language) -> str:
    """The identity form of a surface key_term: stemmed when morphology is enabled
    (``morph_language`` = a language name for Snowball, or ``'auto'`` for the dependency-free
    suffix fallback), else the surface form unchanged. (ADR-003.)"""
    if not morph_language:
        return surface
    lang = None if morph_language == "auto" else morph_language
    return morph.normalize(surface, lang)


def _compose(records, concepts, edges, composition_edges, fingerprints, m_max, min_support) -> int:
    """M>1 composition: coordinate PAIRS that co-occur within a source's unit and recur across
    ≥ ``min_support`` sources become depth-2 composite concepts (a 'these two propositions
    travel together' model). Composite ids are content-derived (a hash of the sorted pair, so
    the same pair in two sources converges), grounded by the co-occurring claims (canonical-
    keyed grounds edges), and added to each source's fingerprint. Only pairs are minted at
    m_max≥2; deeper tuples are a documented extension point. Mutates ``concepts`` / ``edges`` /
    ``fingerprints`` in place; returns the number of composite concepts minted.
    """
    # (source, unit) → {cid → [records]}
    by_unit: dict[tuple, dict] = {}
    for r in records:
        if not r["unit"]:
            continue                     # no unit → can't establish co-occurrence
        by_unit.setdefault((r["source"], r["unit"]), {}).setdefault(r["cid"], []).append(r)

    pair_sources: dict[tuple, set] = {}
    pair_recs: dict[tuple, list] = {}
    for (src, _unit), cidmap in by_unit.items():
        cids = sorted(cidmap)
        for a_i in range(len(cids)):
            for b_i in range(a_i + 1, len(cids)):
                pair = (cids[a_i], cids[b_i])
                pair_sources.setdefault(pair, set()).add(src)
                pair_recs.setdefault(pair, []).extend(cidmap[cids[a_i]] + cidmap[cids[b_i]])

    n_new = 0
    for pair, srcs in pair_sources.items():
        if len(srcs) < min_support:
            continue
        a, b = pair
        comp_id = "m2-" + hashlib.sha1(f"{a}|{b}".encode()).hexdigest()[:12]
        la = concepts.get(a, {}).get("label", a)
        lb = concepts.get(b, {}).get("label", b)
        recs = pair_recs[pair]
        agg = {
            "concept_id": comp_id,
            "coord": {"dimension": "structural", "polarity": "", "predicate": "compose", "modality": "",
                      "quantification": "", "key_term": comp_id, "m": 2,
                      "constituents": [a, b]},
            "label": f"{la}  +  {lb}",
            "surface_key_term": comp_id,
            "dominant_modality": "", "dominant_quantification": "",
            "claims": {r["item_id"] for r in recs},
            "sources": set(srcs),
            "domains": {r["domain"] for r in recs if r["domain"]},
            "example": "", "constituents": [a, b],
        }
        concepts[comp_id] = agg
        for position, constituent in enumerate(pair):
            composition_edges.append({
                "edge_id": "cmp-" + hashlib.sha1(
                    f"{constituent}->{comp_id}".encode()).hexdigest()[:12],
                "src_id": constituent, "dst_id": comp_id, "edge_type": "composes",
                "edge_family": "composition", "dimension": "structural",
                "semantic_role": f"member:{position + 1}", "verification": "candidate",
                "evidence_ids": sorted({r["item_id"] for r in recs}),
                "method_version": "cooccurrence-pair-v1",
            })
        for r in recs:                    # ground the composite by its co-occurring claims
            edges.append({"edge_id": _edge_id(r["item_id"], comp_id),
                          "src_id": r["item_id"], "dst_id": comp_id,
                          "canonical_urn": r["source"], "library": r["library"],
                          "domain": r["domain"]})
            fp = fingerprints.get(r["source"])
            if fp is not None and comp_id not in fp:
                fp.append(comp_id)
        n_new += 1
    for s in fingerprints:                # keep fingerprints sorted/stable
        fingerprints[s] = sorted(fingerprints[s])
    return n_new


def build_canon(claims, m_max: int = 1, axes=IDENTITY_AXES, domain_of=None,
                salience: bool = True, min_df: int = 2, morph_language=None,
                min_support_m: int = 2) -> dict:
    """Cluster ``claims`` into the domain canon by coordinate identity.

    Returns ``{concepts, edges, fingerprints, convergence, n_sources, n_claims}``:

      * ``concepts`` — ``concept_id`` → aggregate ``{concept_id, coord, label, claims,
        sources, domains, dominant_modality, dominant_quantification, example}`` (``claims``
        / ``sources`` / ``domains`` are sets).
      * ``edges`` — one grounds edge per claim: ``{edge_id, src_id(item), dst_id(concept),
        canonical_urn, library, domain}``.
      * ``fingerprints`` — source key → sorted list of its concept_ids (the document's
        mental-model fingerprint).
      * ``convergence`` — the mint curve: for each source (processed in sorted order) the
        cumulative distinct-coordinate count, the count newly minted, and the mint rate.
        A flattening curve is the domain canon ceiling emerging.

    ``salience`` (default) anchors each key_term on the corpus's own salient vocabulary (a
    candidate must be quoted somewhere or recur across ``min_df`` sources) so one-off names
    and OCR noise do not each mint their own concept; set it ``False`` for the raw per-claim
    heuristic. Deterministic and ~O(claims); no model, no network.
    """
    def dom(c):
        return ((domain_of(c) if domain_of else c.get("domain")) or "").strip()

    per_source: dict[str, list] = {}
    n_claims = 0
    for c in claims:
        per_source.setdefault(_source_key(c), []).append(c)
        n_claims += 1

    claim_cands, canonical = ({}, set())
    if salience:
        claim_cands, canonical = _salient_terms(per_source, min_df)

    concepts: dict[str, dict] = {}
    edges: list[dict] = []
    composition_edges: list[dict] = []
    fingerprints: dict[str, list] = {}
    convergence: list[dict] = []
    seen: set[str] = set()
    n_unclustered = 0
    records: list[dict] = []          # per clustered claim, for M>1 composition

    for i, s in enumerate(sorted(per_source), 1):
        s_claims = per_source[s]
        fp: set[str] = set()
        new_here = 0
        for c in s_claims:
            ktv = _pick_key_term((c.get("item_id") or "").strip(), claim_cands, canonical) \
                if salience else None
            # Under salience, a claim with no corpus-salient subject is NOT a mental model —
            # it stays unclustered (a reported residue) rather than collapsing into a giant
            # axes-only bucket that would mean nothing.
            if salience and not ktv:
                n_unclustered += 1
                continue
            # ADR-003: the coordinate identity uses the NORMALIZED key_term (so inflected
            # variants converge); the surface form is kept to pick a readable label.
            surface_kt = ktv if ktv is not None else \
                key_term(c.get("text", ""), c.get("marker", ""))
            ident_kt = _norm_key_term(surface_kt, morph_language) if surface_kt else surface_kt
            coord = coordinate_for(c, m_max=m_max, key_term_value=ident_kt)
            cid = coordinate_id(coord, axes)
            fp.add(cid)
            agg = concepts.get(cid)
            if agg is None:
                agg = concepts[cid] = {
                    "concept_id": cid, "coord": coord, "label": _label(coord),
                    "claims": set(), "sources": set(), "domains": set(),
                    "_mod": {}, "_quant": {}, "_surface": {}, "example": "",
                }
            if surface_kt:
                agg["_surface"][surface_kt] = agg["_surface"].get(surface_kt, 0) + 1
            iid = (c.get("item_id") or "").strip()
            agg["claims"].add(iid)
            agg["sources"].add(s)
            d = dom(c)
            if d:
                agg["domains"].add(d)
            agg["_mod"][coord["modality"]] = agg["_mod"].get(coord["modality"], 0) + 1
            agg["_quant"][coord["quantification"]] = \
                agg["_quant"].get(coord["quantification"], 0) + 1
            if not agg["example"]:
                agg["example"] = (c.get("text") or "")[:200]
            edges.append({
                "edge_id": _edge_id(iid, cid), "src_id": iid, "dst_id": cid,
                "canonical_urn": s, "library": (c.get("library") or "").strip(),
                "domain": d,
            })
            records.append({"source": s, "unit": (c.get("unit_id") or "").strip(),
                            "cid": cid, "item_id": iid,
                            "library": (c.get("library") or "").strip(), "domain": d})
            if cid not in seen:
                seen.add(cid)
                new_here += 1
        fingerprints[s] = sorted(fp)
        convergence.append({
            "i": i, "source": s, "n_distinct": len(seen), "n_new": new_here,
            "n_claims": len(s_claims),
            "mint_rate": (new_here / len(s_claims)) if s_claims else 0.0,
        })

    for agg in concepts.values():
        agg["dominant_modality"] = _dominant(agg.pop("_mod"))
        agg["dominant_quantification"] = _dominant(agg.pop("_quant"))
        # label from the most frequent SURFACE form among the variants this concept merged,
        # so a normalized identity still reads as a real word (ADR-003).
        surface = agg.pop("_surface", {})
        agg["aliases"] = sorted(surface)
        modal_surface = _dominant(surface) if surface else agg["coord"].get("key_term", "")
        agg["surface_key_term"] = modal_surface
        if modal_surface:
            agg["label"] = _label({**agg["coord"], "key_term": modal_surface})

    n_composite = 0
    if m_max >= 2:
        n_composite = _compose(records, concepts, edges, composition_edges,
                               fingerprints, m_max, min_support_m)

    return {"concepts": concepts, "edges": edges,
            "composition_edges": composition_edges, "fingerprints": fingerprints,
            "convergence": convergence, "n_sources": len(per_source),
            "n_claims": n_claims, "n_unclustered": n_unclustered,
            "n_composite": n_composite}


# ── concept-row / canon-entry projections (pure) ──────────────────────────────
def concept_rows(canon: dict, catalogue_version: str = "") -> list[dict]:
    """Materialized concept rows (one per grounding ``canonical_urn`` × concept), in the
    KG-canonical schema: ``canonical_urn, library, concept_id, label, domain, definition,
    catalogue_version, created_by``. Keyed like the materialize step so these rows drop into
    a by-domain ``concepts.csv`` directly.
    """
    lib_dom: dict[tuple, tuple] = {}
    for e in canon["edges"]:
        lib_dom.setdefault((e["dst_id"], e["canonical_urn"]),
                           (e.get("library", ""), e.get("domain", "")))
    rows = []
    for cid, agg in canon["concepts"].items():
        for (c, urn), (lib, d) in ((k, v) for k, v in lib_dom.items() if k[0] == cid):
            rows.append({
                "canonical_urn": urn, "library": lib, "concept_id": cid,
                "label": agg["label"], "domain": d, "definition": "",
                "catalogue_version": catalogue_version, "created_by": "curation:coordinate",
            })
    rows.sort(key=lambda r: (r["canonical_urn"], r["concept_id"]))
    return rows


def edge_rows(canon: dict) -> list[dict]:
    """Materialized grounds-edge rows in the KG-canonical schema: ``canonical_urn, library,
    edge_id, src_id, dst_id, edge_type, rationale, confidence, verification``."""
    rows = [{
        "canonical_urn": e["canonical_urn"], "library": e["library"],
        "edge_id": e["edge_id"], "src_id": e["src_id"], "dst_id": e["dst_id"],
        "edge_type": "grounds", "rationale": "coordinate", "confidence": "",
        "verification": "coordinate", "edge_family": "grounding",
        "dimension": canon["concepts"][e["dst_id"]]["coord"].get("dimension", "relational"),
        "semantic_role": "support", "scope": "", "applicability": "unknown",
        "evidence_ids": json.dumps([e["src_id"]]), "method_version": "coordinate-v1",
    } for e in canon["edges"]]
    rows.sort(key=lambda r: (r["canonical_urn"], r["edge_id"]))
    return rows


def canon_entries(canon: dict) -> list[dict]:
    """Rich per-concept canon entries (JSON), sorted by cross-source support descending."""
    out = []
    for cid, agg in canon["concepts"].items():
        coord = agg["coord"]
        out.append({
            "concept_id": cid, "label": agg["label"],
            "m": coord.get("m", 1), "constituents": coord.get("constituents", []),
            "dimension": coord.get("dimension", "relational"),
            "polarity": coord["polarity"], "predicate": coord["predicate"],
            "key_term": coord["key_term"],
            "surface_key_term": agg.get("surface_key_term", coord["key_term"]),
            "aliases": agg.get("aliases", []),
            "dominant_modality": agg["dominant_modality"],
            "dominant_quantification": agg["dominant_quantification"],
            "n_claims": len(agg["claims"]), "n_sources": len(agg["sources"]),
            "domains": sorted(agg["domains"]), "example": agg["example"],
        })
    out.sort(key=lambda x: (-x["n_sources"], -x["n_claims"], x["concept_id"]))
    return out


# ── partials + merge (for a resumable / per-domain runner) ─────────────────────
def domain_partial(canon: dict, domain: str) -> dict:
    """A compact, mergeable summary of one domain's canon: concept aggregates reduced to
    counts + support sets, plus that domain's per-source fingerprints and convergence. JSON
    round-trippable (sets serialised as sorted lists) so a runner can persist it and resume.
    """
    concepts = {}
    for cid, agg in canon["concepts"].items():
        concepts[cid] = {
            "concept_id": cid, "label": agg["label"], "coord": agg["coord"],
            "surface_key_term": agg.get("surface_key_term", ""),
            "aliases": agg.get("aliases", []),
            "dominant_modality": agg["dominant_modality"],
            "dominant_quantification": agg["dominant_quantification"],
            "claims": sorted(agg["claims"]), "sources": sorted(agg["sources"]),
            "domains": sorted(agg["domains"]), "example": agg["example"],
        }
    return {"domain": domain, "n_sources": canon["n_sources"],
            "n_claims": canon["n_claims"],
            "n_unclustered": canon.get("n_unclustered", 0), "concepts": concepts,
            "fingerprints": canon["fingerprints"],
            "composition_edges": canon.get("composition_edges", [])}


def merge_partials(partials) -> dict:
    """Reduce per-domain partials into a global canon view + global convergence.

    Concept ids are content-derived, so the SAME coordinate seen in two domains merges by
    concept_id — cross-domain convergence falls out. Global convergence is recomputed from
    the union of per-source fingerprints (sources ordered by domain then source key), so its
    flattening reflects the whole corpus's canon ceiling.
    """
    concepts: dict[str, dict] = {}
    canon_by_domain: dict[str, set] = {}
    all_fps: list[tuple] = []           # (domain, source, [concept_ids])
    total_claims = 0
    total_unclustered = 0
    for part in partials:
        d = part.get("domain", "")
        total_claims += int(part.get("n_claims", 0) or 0)
        total_unclustered += int(part.get("n_unclustered", 0) or 0)
        for cid, c in part["concepts"].items():
            agg = concepts.get(cid)
            if agg is None:
                agg = concepts[cid] = {
                    "concept_id": cid, "label": c["label"], "coord": c["coord"],
                    "surface_key_term": c.get("surface_key_term", ""),
                    "aliases": c.get("aliases", []),
                    "dominant_modality": c.get("dominant_modality", ""),
                    "dominant_quantification": c.get("dominant_quantification", ""),
                    "claims": set(), "sources": set(), "domains": set(),
                    "example": c.get("example", ""),
                }
            agg["claims"].update(c.get("claims", []))
            agg["sources"].update(c.get("sources", []))
            agg["domains"].update(c.get("domains", []))
            if not agg["example"]:
                agg["example"] = c.get("example", "")
            canon_by_domain.setdefault(d, set()).add(cid)
        for src, cids in part.get("fingerprints", {}).items():
            all_fps.append((d, src, cids))

    convergence, seen = [], set()
    for i, (d, src, cids) in enumerate(sorted(all_fps, key=lambda t: (t[0], t[1])), 1):
        new_here = sum(1 for c in cids if c not in seen)
        seen.update(cids)
        convergence.append({"i": i, "domain": d, "source": src,
                            "n_distinct": len(seen), "n_new": new_here,
                            "n_coords": len(cids)})

    entries = canon_entries({"concepts": concepts})
    clustered = total_claims - total_unclustered
    return {
        "n_concepts": len(concepts), "n_claims": total_claims,
        "n_unclustered": total_unclustered,
        "clustered_rate": (clustered / total_claims) if total_claims else 0.0,
        "n_sources": len(all_fps),
        "canon_by_domain": {d: len(s) for d, s in sorted(canon_by_domain.items())},
        "concepts": entries, "convergence": convergence,
    }


# ── I/O: curate one materialized by-domain folder, and a whole KG ─────────────
def _read_claims_csv(path: Path) -> list[dict]:
    import csv
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader((line.replace("\x00", "") for line in fh)))


def _write_csv(path: Path, rows, columns) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})


CONCEPT_OUT_COLS = ["canonical_urn", "library", "concept_id", "label", "domain",
                    "definition", "catalogue_version", "created_by"]
EDGE_OUT_COLS = ["canonical_urn", "library", "edge_id", "src_id", "dst_id",
                 "edge_type", "rationale", "confidence", "verification", "edge_family",
                 "dimension", "semantic_role", "scope", "applicability", "evidence_ids",
                 "method_version"]
COMPOSITION_EDGE_COLS = ["edge_id", "src_id", "dst_id", "edge_type", "edge_family",
                         "dimension", "semantic_role", "verification", "evidence_ids",
                         "method_version"]


def curate_domain_folder(folder, domain: str = "", m_max: int = 1,
                         catalogue_version: str = "", morph_language=None) -> dict:
    """Curate ONE materialized by-domain folder in place: read ``claims.csv``, cluster by
    coordinate, and (over)write ``concepts.csv`` + ``semantic_edges.csv`` in that folder in
    the KG-canonical schema. Also writes a ``canon.partial.json`` for the reduce step.
    Returns the partial's headline counts. Reversible in spirit: writes only the two concept
    tables (previously empty) + the partial; never touches ``claims.csv`` or the registry.
    """
    folder = Path(folder).resolve()
    claims = _read_claims_csv(folder / "claims.csv")
    if not domain:
        domain = folder.name
    for c in claims:                              # tag domain if the row lacks one
        c.setdefault("domain", domain)
    canon = build_canon(claims, m_max=m_max, domain_of=lambda c: c.get("domain", domain),
                        morph_language=morph_language)
    _write_csv(folder / "concepts.csv", concept_rows(canon, catalogue_version),
               CONCEPT_OUT_COLS)
    _write_csv(folder / "semantic_edges.csv", edge_rows(canon), EDGE_OUT_COLS)
    comp_rows = []
    for e in canon.get("composition_edges", []):
        row = dict(e)
        row["evidence_ids"] = json.dumps(row.get("evidence_ids", []), sort_keys=True)
        comp_rows.append(row)
    _write_csv(folder / "composition_edges.csv", comp_rows, COMPOSITION_EDGE_COLS)
    partial = domain_partial(canon, domain)
    (folder / "canon.partial.json").write_text(
        json.dumps(partial, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return {"domain": domain, "n_claims": canon["n_claims"],
            "n_sources": canon["n_sources"], "n_concepts": len(canon["concepts"]),
            "n_edges": len(canon["edges"]), "n_unclustered": canon.get("n_unclustered", 0)}


def _load_config(path):
    from ..sync import load_config
    return load_config(path)


def _by_domain_root(cfg: dict) -> Path:
    kg_root = Path(cfg["kg_root"]).expanduser()
    bd = kg_root / "by-domain"
    return bd if bd.is_dir() else kg_root


def curate_kg(config, m_max: int = 1) -> dict:
    """Curate a whole materialized KG (config-driven): run :func:`curate_domain_folder` over
    every ``by-domain/<domain>/`` folder, then merge the partials into ``canon.json`` and
    ``convergence.json`` at the KG root. Single-process; the resumable/parallel Terminal
    runner (``curate_full.py``) reuses these same functions.
    """
    cfg = _load_config(config) if isinstance(config, (str, Path)) else config
    root = _by_domain_root(cfg)
    cat = str(cfg.get("catalogue_version", "") or "")
    morph_language = cfg.get("morph_language")
    domains = sorted(p for p in root.iterdir()
                     if p.is_dir() and (p / "claims.csv").exists())
    partials, per_domain = [], []
    for d in domains:
        r = curate_domain_folder(d, domain=d.name, m_max=m_max, catalogue_version=cat,
                                 morph_language=morph_language)
        per_domain.append(r)
        partials.append(json.loads((d / "canon.partial.json").read_text(encoding="utf-8")))
    merged = merge_partials(partials)
    out_root = Path(cfg["kg_root"]).expanduser()
    (out_root / "canon.json").write_text(
        json.dumps({"m_max": m_max, "identity_axes": list(IDENTITY_AXES),
                    "n_domains": len(domains), **{k: merged[k] for k in
                    ("n_concepts", "n_claims", "n_unclustered", "clustered_rate",
                     "n_sources", "canon_by_domain", "concepts")}},
                   ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (out_root / "convergence.json").write_text(
        json.dumps({"m_max": m_max, "curve": merged["convergence"]},
                   ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {"n_domains": len(domains), "n_concepts": merged["n_concepts"],
            "n_claims": merged["n_claims"], "n_unclustered": merged["n_unclustered"],
            "clustered_rate": merged["clustered_rate"], "n_sources": merged["n_sources"],
            "canon_by_domain": merged["canon_by_domain"], "per_domain": per_domain}
