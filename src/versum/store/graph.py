"""Domain-general three-level graph model — Source 1:1← Claim n:m← Concept.

Plain CSV persistence (stdlib ``csv``), no domain vocabulary anywhere. Concepts carry
their own identity (slug ids that are never source-derived); claims are span-anchored
candidate items; ``grounds`` edges weave the many-to-many fabric from a claim item to a
concept. Two traversals realise the many-to-many law (source → n models, model → n
sources); the invariants keep the fabric well-formed.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field, asdict

CONCEPT_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
EDGE_TYPES = ("grounds", "rhymes_with", "part_of", "application_of", "binds",
              "scope_relation", "composes", "system_relation")

CONCEPT_COLUMNS = ["concept_id", "label", "domain", "definition",
                   "catalogue_version", "created_by", "status", "superseded_by",
                   "aliases"]
EDGE_COLUMNS = ["edge_id", "src_id", "dst_id", "edge_type",
                "rationale", "confidence", "verification", "edge_family",
                "dimension", "semantic_role", "scope", "applicability",
                "evidence_ids", "method_version", "local_predicate", "system_id",
                "system_version", "source_ref"]


# ── dataclasses ──────────────────────────────────────────────────
@dataclass
class Concept:
    concept_id: str
    label: str = ""
    domain: str = ""
    definition: str = ""
    catalogue_version: str = ""
    created_by: str = ""
    status: str = "confirmed"
    superseded_by: str = ""
    aliases: str = ""

    def row(self) -> dict:
        return asdict(self)


@dataclass
class Edge:
    edge_id: str
    src_id: str
    dst_id: str
    edge_type: str
    rationale: str = ""
    confidence: str = ""
    verification: str = "candidate"
    edge_family: str = "semantic"
    dimension: str = "relational"
    semantic_role: str = ""
    scope: str = ""
    applicability: str = "unknown"
    evidence_ids: str = ""
    method_version: str = ""
    local_predicate: str = ""
    system_id: str = ""
    system_version: str = ""
    source_ref: str = ""

    def row(self) -> dict:
        return asdict(self)


@dataclass
class Claim:
    """A flattened claim row (span split into span_start/span_end + profile stamp)."""
    item_id: str
    source_urn: str
    unit_id: str = ""
    unit_type: str = ""
    span_start: int = 0
    span_end: int = 0
    marker: str = ""
    text: str = ""
    polarity: str = ""
    type: str = ""
    predicate: str = ""
    modality: str = ""
    quantification: str = ""
    principle: str = ""
    judicial_canon: str = ""
    inference_rule: str = ""
    confidence: str = ""
    verification: str = "candidate"
    profile: str = ""
    # Universal 5D projection of the profile-local predicate. Empty for a
    # normative (operator) claim — see ``versum.io.extract.candidate_items`` — whose
    # action type is never asserted here, on this or any other claims.csv row: it lives
    # only as a not-asserted entry in the entry model (``entries.csv`` /
    # ``entry_claims.jsonl``, :mod:`versum.planes`), linked from its sentence/claim
    # entry by the structural "embeds" relation and referenced by the owning plane's
    # own action nD coordinate — never by a second claims.csv row.
    dimension: str = ""

    def row(self) -> dict:
        return asdict(self)


def _as_dict(obj) -> dict:
    return obj.row() if hasattr(obj, "row") else dict(obj)


# ── claim flattening ─────────────────────────────────────────────
def flatten_claim(claim: dict, profile_id: str) -> dict:
    """Flatten an extractor item (span list -> span_start/span_end) + profile stamp."""
    row: dict = {}
    for k, v in claim.items():
        if k == "span" and isinstance(v, (list, tuple)) and len(v) == 2:
            row["span_start"], row["span_end"] = v[0], v[1]
        else:
            row[k] = v
    row["profile"] = profile_id
    return row


# ── CSV persistence ──────────────────────────────────────────────
def _write_csv(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})


def save_concepts(path, concepts) -> None:
    _write_csv(path, [_as_dict(c) for c in concepts], CONCEPT_COLUMNS)


def load_concepts(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def save_edges(path, edges) -> None:
    _write_csv(path, [_as_dict(e) for e in edges], EDGE_COLUMNS)


def load_edges(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class ClaimProvenanceError(ValueError):
    """A row offered to :func:`save_claims` has no asserted provenance chain.

    ``claims.csv`` is the candidate-claim layer a curator confirms — every row on it
    must be traceable to an asserted verification plus the source/span it was read off.
    This is the Phase 0 write-boundary invariant (``docs/architecture/planes.md``): a
    norm's action type/content is NEVER written to ``claims.csv``, under any
    verification, dimension or column name — it lives only as a not-asserted entry in
    the entry model (``entries.csv`` / ``entry_claims.jsonl``, :mod:`versum.planes`),
    linked by the structural "embeds" relation. A row stamped ``verification`` outside
    the asserted vocabulary (e.g. the reverted ``"structural"`` companion-row marker), or
    missing its ``source_urn`` / span, raises here instead of ever reaching disk.
    """


#: The claims.csv verification vocabulary that DOES carry an asserted provenance chain —
#: a candidate a curator can confirm, a confirmed curation decision, or an attested
#: registry/sidecar fact. Anything else (e.g. ``"structural"``, ``"not_declared"``, or a
#: missing value on a non-empty row) is not an assertion this store may persist here.
ASSERTED_CLAIM_VERIFICATIONS = frozenset({"candidate", "confirmed", "attested"})


def _check_claim_provenance(row: dict) -> None:
    verification = row.get("verification")
    if verification not in (None, "") and verification not in ASSERTED_CLAIM_VERIFICATIONS:
        raise ClaimProvenanceError(
            f"claim {row.get('item_id')!r} has verification {verification!r}, not an "
            f"asserted provenance chain ({sorted(ASSERTED_CLAIM_VERIFICATIONS)!r}); a "
            "norm's action type/content may never be written to claims.csv — see "
            "versum.planes' entry model (entries.csv / entry_claims.jsonl, the "
            "structural 'embeds' relation) instead")
    if not row.get("source_urn"):
        raise ClaimProvenanceError(
            f"claim {row.get('item_id')!r} has no source_urn — every claims.csv row "
            "must carry an asserted source")
    if row.get("span_start") is None or row.get("span_end") is None:
        raise ClaimProvenanceError(
            f"claim {row.get('item_id')!r} has no span — every claims.csv row must "
            "carry an asserted span into its source")


def save_claims(path, claims, profile_id: str) -> None:
    """Persist claims; each is flattened (span -> span_start/span_end) + profile.

    Write-boundary invariant (Phase 0): every row must carry an asserted provenance
    chain — a recognised ``verification`` plus a ``source_urn`` and a span — or this
    raises :class:`ClaimProvenanceError` before anything is written. This is what keeps
    a norm's action type/content out of ``claims.csv`` for good: the reverted
    companion-row design tagged such a row ``verification="structural"``, which is
    exactly the shape this check refuses.
    """
    rows = [flatten_claim(_as_dict(c), profile_id) for c in claims]
    for row in rows:
        _check_claim_provenance(row)
    columns = list(rows[0].keys()) if rows else (
        [f.name for f in Claim.__dataclass_fields__.values()])
    _write_csv(path, rows, columns)


def load_claims(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("span_start", "span_end"):
            if r.get(k) not in (None, ""):
                r[k] = int(r[k])
    return rows


# ── traversals (the many-to-many law) ────────────────────────────
def models_for_source(urn: str, claims, edges) -> set:
    """source → n models: claims of this source → their item_ids → grounds dst concepts."""
    item_ids = {_as_dict(c)["item_id"] for c in claims
                if _as_dict(c).get("source_urn") == urn}
    out = set()
    for e in edges:
        e = _as_dict(e)
        if e.get("edge_type") == "grounds" and e.get("src_id") in item_ids:
            out.add(e.get("dst_id"))
    return out


def sources_for_model(concept_id: str, claims, edges) -> set:
    """model → n sources: grounds edges to this concept → src item_ids → their urns."""
    item_ids = {_as_dict(e).get("src_id") for e in edges
                if _as_dict(e).get("edge_type") == "grounds"
                and _as_dict(e).get("dst_id") == concept_id}
    return {_as_dict(c).get("source_urn") for c in claims
            if _as_dict(c).get("item_id") in item_ids}


# ── invariants (each returns a list of violations; empty = ok) ────
def check_no_orphan_claims(claims, known_urns) -> list:
    known = set(known_urns)
    out = []
    for c in claims:
        c = _as_dict(c)
        if c.get("source_urn") not in known:
            out.append(f"claim {c.get('item_id')} has unknown source_urn "
                       f"{c.get('source_urn')!r}")
    return out


def check_no_orphan_edges(claims, concepts, edges) -> list:
    item_ids = {_as_dict(c).get("item_id") for c in claims}
    concept_ids = {_as_dict(c).get("concept_id") for c in concepts}
    out = []
    for e in edges:
        e = _as_dict(e)
        et = e.get("edge_type")
        if et == "grounds":
            if e.get("src_id") not in item_ids:
                out.append(f"edge {e.get('edge_id')} src {e.get('src_id')!r} "
                           f"is not a known claim")
            if e.get("dst_id") not in concept_ids:
                out.append(f"edge {e.get('edge_id')} dst {e.get('dst_id')!r} "
                           f"is not a known concept")
        else:
            for end in ("src_id", "dst_id"):
                if e.get(end) not in concept_ids:
                    out.append(f"edge {e.get('edge_id')} {end} {e.get(end)!r} "
                               f"is not a known concept")
    return out


def check_concept_ids_own_identity(concepts, known_urns=frozenset()) -> list:
    """A concept_id must be a slug (^[a-z][a-z0-9-]*$), never a urn, never a source urn."""
    known = set(known_urns)
    out = []
    for c in concepts:
        cid = _as_dict(c).get("concept_id", "")
        if not CONCEPT_ID_RE.match(cid or ""):
            out.append(f"concept_id {cid!r} is not a bare slug")
        if (cid or "").startswith("urn:"):
            out.append(f"concept_id {cid!r} is a urn (must own its identity)")
        if cid in known:
            out.append(f"concept_id {cid!r} equals a known source urn")
    return out


# ── typed edge constructors and contracts ───────────────────────
EDGE_FAMILIES = frozenset({
    "provenance", "grounding", "binding", "scope", "semantic", "composition"})


def grounding_edge(edge_id: str, claim_id: str, concept_id: str, *, role="support",
                   dimension="relational", evidence_ids=(), verification="candidate") -> dict:
    return Edge(edge_id, claim_id, concept_id, "grounds", verification=verification,
                edge_family="grounding", dimension=dimension, semantic_role=role,
                evidence_ids=json.dumps(sorted(evidence_ids))).row()


def binding_edge(edge_id: str, claim_id: str, assignment_id: str, *, form_slot: str,
                 dimension="relational", evidence_ids=(), verification="candidate") -> dict:
    return Edge(edge_id, claim_id, assignment_id, "binds", verification=verification,
                edge_family="binding", dimension=dimension, semantic_role=form_slot,
                evidence_ids=json.dumps(sorted(evidence_ids))).row()


def scope_edge(edge_id: str, left_id: str, right_id: str, *, primitive: str,
               scope=None, evidence_ids=(), verification="candidate") -> dict:
    return Edge(edge_id, left_id, right_id, "scope_relation", verification=verification,
                edge_family="scope", semantic_role=primitive,
                scope=json.dumps(scope or {}, sort_keys=True),
                evidence_ids=json.dumps(sorted(evidence_ids))).row()


def composition_edge(edge_id: str, component_id: str, composition_id: str, *, role: str,
                     dimension="structural", evidence_ids=(),
                     verification="candidate") -> dict:
    return Edge(edge_id, component_id, composition_id, "composes",
                verification=verification, edge_family="composition",
                dimension=dimension, semantic_role=role,
                evidence_ids=json.dumps(sorted(evidence_ids))).row()


def check_edge_contracts(edges) -> list[str]:
    """Validate edge family/type/dimension and required semantic roles.

    Legacy rows with no ``edge_family`` remain readable and are interpreted as semantic
    edges. Newly typed families receive stricter checks.
    """
    from ..dimensions import Dimension
    out = []
    family_types = {
        "grounding": {"grounds"}, "binding": {"binds"},
        "scope": {"scope_relation"}, "composition": {"composes"},
    }
    role_required = {"grounding", "binding", "scope", "composition"}
    for raw in edges:
        e = _as_dict(raw)
        eid = e.get("edge_id", "")
        family = e.get("edge_family") or "semantic"
        if family not in EDGE_FAMILIES:
            out.append(f"edge {eid}: unknown edge_family {family!r}")
        allowed = family_types.get(family)
        if allowed and e.get("edge_type") not in allowed:
            out.append(f"edge {eid}: type {e.get('edge_type')!r} invalid for {family}")
        try:
            Dimension(e.get("dimension") or "relational")
        except ValueError:
            out.append(f"edge {eid}: invalid 5D dimension {e.get('dimension')!r}")
        if family in role_required and not e.get("semantic_role"):
            out.append(f"edge {eid}: {family} edge requires semantic_role")
        if not e.get("src_id") or not e.get("dst_id"):
            out.append(f"edge {eid}: endpoints are required")
    return out


def deprecate_concepts(concepts, replacements: dict[str, str]) -> list[dict]:
    """Apply a lossless concept replacement map.

    Replaced rows remain present with ``status=deprecated`` and ``superseded_by``. Their ids
    and labels are added to the surviving concept's aliases. No grounding edge is rewritten
    here; migrations can redirect edges separately while retaining the old rows as lineage.
    """
    rows = [_as_dict(c).copy() for c in concepts]
    by_id = {r.get("concept_id"): r for r in rows}
    for old, new in replacements.items():
        if old not in by_id:
            raise KeyError(f"unknown deprecated concept {old!r}")
        if new not in by_id:
            raise KeyError(f"unknown replacement concept {new!r}")
        if old == new:
            raise ValueError("a concept cannot supersede itself")
        prior = by_id[old]
        prior["status"] = "deprecated"
        prior["superseded_by"] = new
        survivor = by_id[new]
        aliases = survivor.get("aliases") or "[]"
        if isinstance(aliases, str):
            try:
                aliases = json.loads(aliases)
            except json.JSONDecodeError:
                aliases = [aliases] if aliases else []
        aliases = set(aliases or [])
        aliases.update(x for x in (old, prior.get("label")) if x)
        survivor["aliases"] = json.dumps(sorted(aliases), ensure_ascii=False)
    return rows
