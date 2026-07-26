"""Per-source fingerprint — a fixed-shape aggregate of a source's claims.

``dim5`` is a histogram over the profile's closed axes (predicate / modality /
quantification / polarity): its keys are drawn from the profile's sets, so the shape is
fixed per profile and fingerprints are comparable within a corpus. The ``polarity`` axis
counts the descriptive/normative value each claim already carries (stamped upstream by the
extractor) — its universe comes from the profile when it exposes ``polarities``, else the
neutral ``{'D','N'}`` encoding; no domain value is named here. ``nd`` holds coordinate-sets:
``namespace`` is known from the profile, and ``jurisdiction`` / ``time`` are populated from
an optional ``nd_context`` (READ from the registry, never inferred) — left empty when no
context is supplied, never fabricated. Pure aggregate — no domain value is hardcoded here.

The ``principle`` and ``canon`` coordinates are intentionally NOT aggregated at index time:
they are curator-confirmed values filled later at curation, not read from candidate claims.
"""
from __future__ import annotations

from ..dimensions import dimension_values


def _as_dict(obj) -> dict:
    return obj.row() if hasattr(obj, "row") else dict(obj)


def _hist(values, universe) -> dict:
    h = {v: 0 for v in sorted(universe)}
    for v in values:
        if v in h:
            h[v] += 1
    return h


def _coord_set(ctx, key) -> set:
    """Normalise one nd coordinate from ``ctx`` into a deduped set of non-empty strings.

    Accepts a scalar or any iterable of scalars; empty / missing values yield an empty set
    so an unknown coordinate stays empty rather than being invented.
    """
    if not ctx:
        return set()
    val = ctx.get(key)
    if val is None or val == "":
        return set()
    if isinstance(val, (set, frozenset, list, tuple)):
        return {str(v).strip() for v in val if str(v).strip()}
    s = str(val).strip()
    return {s} if s else set()


def fingerprint(source_urn: str, claims, profile, nd_context=None) -> dict:
    """Aggregate the claims of ``source_urn`` into a fixed-shape fingerprint.

    ``nd_context`` (optional) is a ``{jurisdiction, time}`` mapping READ from the source's
    registry row (loop 4). When supplied it populates ``nd.jurisdiction`` / ``nd.time`` as
    deduped sets; when absent those coordinates stay empty (unchanged behaviour). No
    classification is performed — the values are read, not inferred.
    """
    rel = [_as_dict(c) for c in claims if _as_dict(c).get("source_urn") == source_urn]
    polarities = getattr(profile, "polarities", None) or {"D", "N"}
    dim5 = {
        "predicate": _hist((c.get("predicate") for c in rel), profile.predicates),
        "modality": _hist((c.get("modality") for c in rel), profile.modalities),
        "quantification": _hist((c.get("quantification") for c in rel),
                                profile.quantifications),
        "polarity": _hist((c.get("polarity") for c in rel), polarities),
    }
    federation_5d = _hist((c.get("dimension") for c in rel), dimension_values())
    nd = {
        "namespace": profile.namespace,
        "jurisdiction": _coord_set(nd_context, "jurisdiction"),
        "time": _coord_set(nd_context, "time"),
    }
    return {
        "source_urn": source_urn,
        "profile": profile.id,
        "n_claims": len(rel),
        "dim5": dim5,
        # Canonical names. ``dim5`` and ``nd`` remain as compatibility projections until
        # consumers migrate; they are the profile-local claim-form histogram and context.
        "federation_5d": federation_5d,
        "form_profile": dim5,
        "context_footprint": nd,
        "concept_footprint": [],
        "nd": nd,
    }
