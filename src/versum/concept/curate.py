"""versum/curate.py — the curation loop: claim → concept suggester.

Turns the concept layer from hand-authored into *suggested-then-confirmed*, keeping the
same discipline as the write guard: **deterministic first, LLM only as an escalation.**

Three deterministic rungs, no model required:

  1. **Seed concepts from definitions.** A definitional claim ("'personal data' means …")
     names a concept — the defined term becomes a candidate concept (own-identity slug).
  1.5 **Seed concepts from cross-source recurrence.** Terms (1–3-word grams) that recur
     in claims of at least two distinct sources become candidate concepts. No *domain*
     vocabulary is hardcoded: function words are excluded by a closed-class EN+DE list
     (language structure, like the morph suffix tables) plus a statistical ceiling — a
     token present in more than a third of all claims is corpus plumbing whatever its
     language — plus the extraction profiles' own marker words (claims exist because a
     marker matched, so markers recur by construction). Grams are keyed by their morph
     stem, so inflections (werk/werke/werkes) aggregate into ONE candidate carrying
     every surface form as a label; grams are kept maximal (a shorter gram subsumed by
     a longer one with equal support is dropped).
  2. **Link by mention.** Any claim whose text mentions a candidate concept's label gets a
     suggested ``grounds`` edge to it, scored by support (how many claims / how many
     distinct sources — cross-source support = convergence).

Output is a *curation queue* (`.versum/curation/`), never a direct graph write. The
curator (a human, or an injected ``judge`` ladder — local model first) confirms; only
``confirm()`` promotes suggestions into `concepts.csv` + `semantic_edges.csv`. Nothing is
fabricated: a concept only exists if a definition seeded it or the curator adds it.
"""
from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

from ..store import graph as g
from .morph import normalize, stem_word, transliterate

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", transliterate(s)).strip("-")[:60]


_TOKEN_RE = re.compile(r"[^\W\d_]+")

# Closed-class function words (EN+DE, the languages of the built-in profiles):
# articles, prepositions, pronouns, conjunctions, auxiliaries, modals, quantifiers.
# A finite, enumerable *language-structure* list — the same category as extract.py's
# _DEF_STRIP and morph.py's suffix tables, never domain vocabulary. It complements
# the statistical ceiling below, which alone cannot separate a mid-frequency
# function word from a mid-frequency term in a small mixed-language corpus.
FUNCTION_WORDS = frozenset("""
the and for are was were has have had not but with from this that these those its
his her their our your all any each both few more most other some such only own
same than too very can will just shall may might must should would could does did
doing being been also into onto over under between through during before after
above below again further then once here there when where why how what which who
whom while about against
der die das den dem des ein eine einer eines einem einen und oder aber auch nicht
kein keine mit von aus bei nach ueber unter zwischen durch gegen ohne um zu zur
zum im in am an auf fuer ist sind war waren wird werden wurde wurden hat haben
hatte hatten kann koennen koennt konnte muss muessen musste soll sollen sollte darf
duerfen durfte mag moegen wollte wollen sich ihr ihre ihrer euer eure unser
unsere dieser diese dieses jener jene jenes alle jeder jede jedes einige manche
solche welche wenn dann denn weil dass damit sowie beim vom als wie noch schon
nur mehr sehr man hier dort auch etwa bzw ggf inkl habt meist siehe
sie sein seine seiner seinen seinem dies diese dieser dieses diesem denen ihm ihn
ihnen bis vor sowie jedoch sofern soweit bereits andere anderen anderer anderes
anderem abs ziff nr vgl
one two three first second als also
""".split())


def _is_function_word(token: str) -> bool:
    """Membership check in surface OR transliterated form, so ``für`` matches the
    ASCII list entry ``fuer`` and inflected umlaut forms (``könnt``) fold likewise."""
    return token in FUNCTION_WORDS or transliterate(token) in FUNCTION_WORDS

# recurrence-mining thresholds: statistical complement to FUNCTION_WORDS. A token in
# more than MAX_CLAIM_SHARE of all claims is function-word plumbing even if unlisted
# (covers languages beyond EN/DE); a gram needs MIN_CLAIMS mentions across
# MIN_SOURCES distinct sources to count as a recurring term.
MIN_SOURCES = 2
MIN_CLAIMS = 3
MAX_CLAIM_SHARE = 1 / 3
MAX_MINED_TERMS = 40
_MIN_TOKEN_LEN = 3
_SUBSUME_SHARE = 0.8


def _marker_tokens(claims) -> frozenset:
    """Tokens of the extraction profiles' own marker patterns and def_verbs.

    Claims exist BECAUSE a marker matched, so marker words recur by construction —
    mining them measures the extractor, not the corpus. The profiles stamped on the
    claims tell us exactly which words those are; nothing is hardcoded here."""
    from ..profile import get_profile
    toks: set[str] = set()
    for pid in {c.get("profile") for c in claims if c.get("profile")}:
        try:
            p = get_profile(pid)
        except Exception:
            continue
        for entry in p.markers:
            toks |= {t.lower() for t in _TOKEN_RE.findall(entry[0])}
        toks |= {str(v).lower() for v in p.def_verbs}
    return frozenset(toks)


def _mine_recurring_terms(claims, extra_common=frozenset()) -> list[dict]:
    """Rung 1.5 — deterministic cross-source term mining, no domain vocabulary, no model.

    Grams are keyed by their *stem-normalized* form (morph.stem_word), so inflections
    of one term (werk / werke / werkes) aggregate into a single candidate BEFORE the
    support thresholds — sparse surface forms count toward the family, and the family
    carries every surface variant as a mention label. Returns [{concept_id, label,
    labels, n_claims, n_sources}] for grams that (a) contain no common token at their
    boundary (statistical ceiling ∪ function words ∪ ``extra_common``), (b) appear in
    at least MIN_CLAIMS claims spanning MIN_SOURCES sources, and (c) are maximal — a
    gram subsumed by a longer kept gram with >= SUBSUME_SHARE of its support is
    dropped. Ranked by (sources, claims); capped at MAX_MINED_TERMS.
    """
    per_claim: list[tuple[str, list[str], list[str]]] = []   # (source, lower, orig)
    for c in claims:
        toks = _TOKEN_RE.findall(c.get("text") or "")
        if toks:
            per_claim.append((c.get("source_urn", ""),
                              [t.lower() for t in toks], toks))
    n_claims_total = len(per_claim)
    if n_claims_total < MIN_CLAIMS:
        return []

    tok_claims: dict[str, int] = {}                          # token -> claim df
    for _, low, _ in per_claim:
        for t in set(low):
            tok_claims[t] = tok_claims.get(t, 0) + 1
    common = {t for t, n in tok_claims.items() if n / n_claims_total > MAX_CLAIM_SHARE}
    common |= {t for t in tok_claims if _is_function_word(t)}
    common |= set(extra_common)

    grams: dict[tuple, dict] = {}      # keyed by stem-normalized token tuple
    for src, low, orig in per_claim:
        seen: set[tuple] = set()
        for n in (1, 2, 3):
            for i in range(len(low) - n + 1):
                surface = tuple(low[i:i + n])
                if any(len(t) < _MIN_TOKEN_LEN for t in surface):
                    continue
                if surface[0] in common or surface[-1] in common:
                    continue
                gram = tuple(stem_word(t) for t in surface)
                if gram in seen:
                    continue
                seen.add(gram)
                d = grams.setdefault(gram, {"claims": 0, "sources": set(),
                                            "variants": {}})
                d["claims"] += 1
                d["sources"].add(src)
                v = " ".join(orig[i:i + n])
                d["variants"][v] = d["variants"].get(v, 0) + 1

    qualified = {gram: d for gram, d in grams.items()
                 if len(d["sources"]) >= MIN_SOURCES and d["claims"] >= MIN_CLAIMS
                 and d["claims"] / n_claims_total <= MAX_CLAIM_SHARE}

    # keep maximal grams: drop a gram contained in a kept longer gram with ~same support
    kept: dict[tuple, dict] = {}
    for gram in sorted(qualified, key=lambda t2: (-len(t2), t2)):
        d = qualified[gram]
        subsumed = any(
            len(kg) > len(gram)
            and any(kg[j:j + len(gram)] == gram for j in range(len(kg) - len(gram) + 1))
            and kd["claims"] >= _SUBSUME_SHARE * d["claims"]
            for kg, kd in kept.items())
        if not subsumed:
            kept[gram] = d

    ranked = sorted(kept.items(),
                    key=lambda it: (-len(it[1]["sources"]), -it[1]["claims"], it[0]))
    out = []
    for gram, d in ranked[:MAX_MINED_TERMS]:
        label = min(d["variants"].items(), key=lambda kv: (-kv[1], kv[0]))[0]
        cid = _slug(" ".join(gram))
        if cid:
            out.append({"concept_id": cid, "label": label,
                        "labels": sorted(d["variants"]),
                        "n_claims": d["claims"], "n_sources": len(d["sources"])})
    return out


def _mention_re(label: str) -> re.Pattern:
    """A word-boundary matcher for ``label`` with light plural tolerance: internal
    whitespace tolerant, and an optional trailing ``s`` so 'data subjects' matches the
    seed 'data subject'."""
    parts = [p for p in re.split(r"\s+", label.strip()) if p]
    esc = r"\s+".join(re.escape(p) for p in parts)
    return re.compile(r"\b" + esc + r"s?\b", re.IGNORECASE)


def suggest(claims, definitions, existing_concepts=None):
    """Return (suggested_concepts, suggested_edges) — deterministic, no model.

    ``definitions`` is the clean entity-concept seed list from ``definitions.csv``
    ({term, term_slug, ...}); each becomes a candidate concept (concept_id = term_slug,
    label = term). Then any claim that MENTIONS a concept's label (word-boundary,
    case-insensitive, light plural tolerance) gets a suggested ``grounds`` edge.

    suggested_concepts: list of dicts {concept_id, label, n_claims, n_sources, example}.
    suggested_edges: list of dicts {edge_id, src_id(claim), dst_id(concept), edge_type,
    rationale, confidence, verification}.
    """
    # rung 1 — seed concepts from the clean definition scan
    seeds: dict[str, dict] = {}
    for d in (definitions or []):
        cid = (d.get("term_slug") or _slug(d.get("term", ""))).strip()
        if not cid:
            continue
        label = d.get("term") or cid.replace("-", " ")
        s = seeds.setdefault(cid, {"concept_id": cid, "label": label,
                                   "labels": set(), "example": "",
                                   "seed": "definition"})
        s["labels"].add(label)
    # also treat existing (curator-authored) concepts as link targets
    for c in (existing_concepts or []):
        cid = c.get("concept_id")
        if not cid:
            continue
        s = seeds.setdefault(cid, {"concept_id": cid, "label": c.get("label", cid),
                                   "labels": set(), "example": "",
                                   "seed": "existing"})
        s["labels"].add(c.get("label") or cid)
        s["labels"].add(cid.replace("-", " "))
    # rung 1.5 — seed concepts from cross-source recurrence (definitions win on clash;
    # a mined family folds into a definition/existing seed when their STEMS match, so
    # the mined stem-id 'onlin' lands on the seed 'online' instead of duplicating it).
    # The profiles' own marker words are excluded — they recur by construction.
    stem_of_seed = {}
    for cid in seeds:
        stem_of_seed.setdefault(normalize(cid), cid)
    for m in _mine_recurring_terms(claims, _marker_tokens(claims)):
        cid = m["concept_id"]
        if cid not in seeds:
            cid = stem_of_seed.get(normalize(cid), cid)
        s = seeds.setdefault(cid,
                             {"concept_id": cid, "label": m["label"],
                              "labels": set(), "example": "", "seed": "recurrence"})
        s["labels"].update(m.get("labels", ()))
        s["labels"].add(m["label"])
        s["labels"].add(m["concept_id"].replace("-", " "))

    compiled = {cid: [_mention_re(lbl) for lbl in s["labels"] if lbl]
                for cid, s in seeds.items()}

    # rung 2 — link any claim that mentions a concept label
    edges, per_concept = [], {}
    for c in claims:
        text = c.get("text") or ""
        for cid, s in seeds.items():
            if any(r.search(text) for r in compiled[cid]):
                eid = "sug-" + hashlib.sha1(
                    f"{c['item_id']}{cid}".encode()).hexdigest()[:10]
                edges.append({"edge_id": eid, "src_id": c["item_id"], "dst_id": cid,
                              "edge_type": "grounds", "rationale": "mention",
                              "confidence": "", "verification": "suggested"})
                d = per_concept.setdefault(cid, {"claims": set(), "sources": set()})
                d["claims"].add(c["item_id"]); d["sources"].add(c.get("source_urn"))
                if not s["example"]:
                    s["example"] = text[:120]

    suggested_concepts = []
    for cid, s in seeds.items():
        pc = per_concept.get(cid, {"claims": set(), "sources": set()})
        if not pc["claims"]:
            continue  # a concept nobody mentions is not worth suggesting
        suggested_concepts.append({
            "concept_id": cid, "label": s["label"],
            "n_claims": len(pc["claims"]), "n_sources": len(pc["sources"]),
            "seed": s.get("seed", "definition"), "example": s["example"]})
    suggested_concepts.sort(key=lambda x: (-x["n_sources"], -x["n_claims"]))
    return suggested_concepts, edges


# ── queue persistence ────────────────────────────────────────────
def _qdir(folder) -> Path:
    d = Path(folder).resolve() / ".versum" / "curation"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_definitions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def suggest_folder(folder) -> dict:
    v = Path(folder).resolve() / ".versum"
    claims = g.load_claims(v / "claims.csv")
    definitions = _load_definitions(v / "definitions.csv")
    existing = g.load_concepts(v / "concepts.csv") if (v / "concepts.csv").exists() else []
    concepts, edges = suggest(claims, definitions, existing)
    q = _qdir(folder)
    with open(q / "suggested_concepts.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["concept_id", "label", "n_claims",
                                            "n_sources", "seed", "example"])
        wr.writeheader(); wr.writerows(concepts)
    g.save_edges(q / "suggested_edges.csv", edges)
    return {"n_suggested_concepts": len(concepts), "n_suggested_edges": len(edges),
            "cross_source": sum(1 for c in concepts if c["n_sources"] > 1),
            "n_recurrence": sum(1 for c in concepts if c["seed"] == "recurrence")}


def confirm_folder(folder, min_sources=1, only_concepts=None) -> dict:
    """Promote suggestions into the graph. Filter by support or an explicit allowlist.

    min_sources: keep only concepts grounded from at least this many distinct sources
    (min_sources=2 keeps only convergent, cross-source concepts). only_concepts: an
    explicit set of concept_ids to accept (curator's pick), overriding the threshold.
    """
    q = _qdir(folder)
    with open(q / "suggested_concepts.csv", newline="", encoding="utf-8") as fh:
        sc = list(csv.DictReader(fh))
    se = g.load_edges(q / "suggested_edges.csv")
    keep = {c["concept_id"] for c in sc
            if (only_concepts and c["concept_id"] in only_concepts)
            or (not only_concepts and int(c["n_sources"]) >= min_sources)}
    concepts = [g.Concept(c["concept_id"], c["label"], "", c.get("example", ""),
                          "", "curation:auto").row()
                for c in sc if c["concept_id"] in keep]
    edges = [e for e in se if e["dst_id"] in keep]
    for e in edges:
        e["verification"] = "confirmed"
    v = Path(folder).resolve() / ".versum"
    g.save_concepts(v / "concepts.csv", concepts)
    g.save_edges(v / "semantic_edges.csv", edges)
    return {"n_concepts": len(concepts), "n_edges": len(edges),
            "concept_ids": sorted(keep)}
