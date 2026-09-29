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


def _coord_interval(val) -> dict | None:
    """The canonical ``{from, to}`` interval carried by ``val``, else ``None``.

    Only a ``{"from": ..., "to": ...}`` dict with both endpoints non-empty is an
    interval; anything else (a bare point string, a list, ``None``) is not — it stays
    a point, handled by :func:`_coord_set` as before.
    """
    if not isinstance(val, dict):
        return None
    frm = str(val.get("from") or "").strip()
    to = str(val.get("to") or "").strip()
    return {"from": frm, "to": to} if frm and to else None


def _coord_value(ctx, key):
    """The nd coordinate for ``key``: a single interval dict when interval-shaped,
    else the deduped point set — unchanged behaviour for every non-interval value."""
    interval = _coord_interval(ctx.get(key)) if ctx else None
    return interval if interval is not None else _coord_set(ctx, key)


def coord_values(ctx, axis_id) -> list:
    """Assignment-ready values for one nd axis: ONE canonical interval when
    ``axis_id`` carries an interval-shaped value, else the sorted point set — this is
    the identical list :func:`_coord_set` produced before intervals existed.
    """
    if ctx:
        interval = _coord_interval(ctx.get(axis_id))
        if interval is not None:
            return [interval]
    return sorted(_coord_set(ctx, axis_id))


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
    dimensions_5d = _hist((c.get("dimension") for c in rel), dimension_values())
    nd = {
        "namespace": profile.namespace,
        "jurisdiction": _coord_set(nd_context, "jurisdiction"),
        "time": _coord_value(nd_context, "time"),
    }
    return {
        "source_urn": source_urn,
        "profile": profile.id,
        "n_claims": len(rel),
        "dim5": dim5,
        # Canonical names. ``dim5`` and ``nd`` remain as compatibility projections until
        # consumers migrate; they are the profile-local claim-form histogram and context.
        "dimensions_5d": dimensions_5d,
        "form_profile": dim5,
        "context_footprint": nd,
        "concept_footprint": [],
        "nd": nd,
    }


# Key renamed in this release; stores written before it still carry the old key.
_RENAMED_KEYS = {"federation_5d": "dimensions_5d"}


def upgrade_fingerprint(fp):
    """Return ``fp`` with renamed keys under their current names.

    A fingerprint read from an older ``fingerprints.json`` may carry a key under its
    previous name; the current name wins when both are present. Non-dict values pass
    through unchanged.
    """
    if not isinstance(fp, dict):
        return fp
    out = dict(fp)
    for old, new in _RENAMED_KEYS.items():
        if old in out:
            value = out.pop(old)
            out.setdefault(new, value)
    return out


def upgrade_fingerprint_store(store):
    """Apply :func:`upgrade_fingerprint` to every value of a ``{urn: fingerprint}`` store."""
    if not isinstance(store, dict):
        return store
    return {urn: upgrade_fingerprint(fp) for urn, fp in store.items()}

