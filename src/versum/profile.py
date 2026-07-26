"""Profile abstraction — the pluggable domain vocabulary for the versum framework.

A ``Profile`` carries every domain-specific value the framework needs: the closed
catalogues for each axis, the surface-marker tables, the instrument-rank ladder and
the URN namespace. Framework modules (extract / graph / fingerprint) never hardcode a
catalogue value; they always ask the active profile. This is the dependency-inversion
boundary from ADR-001: the framework depends on the ``Profile`` interface, and each
domain plugs in by supplying values only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .dimensions import DEFAULT_DIMENSION, Dimension


@dataclass(frozen=True)
class Profile:
    """A closed, per-domain vocabulary passed into the framework.

    Fields carry values only — no framework logic lives here. ``markers`` is a tuple of
    ``(pattern, predicate, modality)`` surface rules; ``quant_cues`` is a tuple of
    ``(value, cues)`` where ``cues`` is a tuple of lowercased trigger substrings.
    ``modalities_n`` names the subset of ``modalities`` that carry normative polarity
    (everything else is descriptive); it lets the extractor stamp polarity without
    knowing any domain term.
    """

    id: str
    namespace: str
    catalogue_version: str
    predicates: frozenset
    modalities: frozenset
    quantifications: frozenset
    principles: frozenset
    canons: frozenset
    inference_rules: frozenset
    instrument_rank: dict
    markers: tuple
    quant_cues: tuple
    modalities_n: frozenset = field(default_factory=frozenset)
    def_verbs: frozenset = field(default_factory=frozenset)
    # deterministic identity resolvers (rung 0), supplied by the domain, not the core:
    # an ordered tuple of ``(scheme, compiled_pattern)``. The write guard tries each in
    # order against the filename/metadata; the first whose ``group(1)`` matches yields
    # ``urn:<namespace>:<scheme>:<id>``. Empty ⇒ the guard falls straight to the path-slug.
    source_identifiers: tuple = ()
    # Profile-local predicate -> universal Federation-5D edge dimension.  Local predicates
    # retain their finer meaning; this projection is the cross-profile comparison seam.
    predicate_dimensions: dict = field(default_factory=dict)

    def __post_init__(self):
        unknown = set(self.predicate_dimensions) - set(self.predicates)
        if unknown:
            raise ValueError(f"predicate dimension mapping names unknown predicates: {unknown}")
        for predicate, dimension in self.predicate_dimensions.items():
            try:
                Dimension(dimension)
            except ValueError as exc:
                raise ValueError(
                    f"predicate {predicate!r} maps to unknown Federation dimension "
                    f"{dimension!r}") from exc

    def dimension_for(self, predicate: str) -> str:
        """Project a local predicate onto Federation-5D.

        Unmapped values use the relational safe floor while remaining visibly unmapped via
        :meth:`unmapped_predicates`; callers never lose the original local predicate.
        """
        return Dimension(self.predicate_dimensions.get(
            predicate, DEFAULT_DIMENSION.value)).value

    def unmapped_predicates(self) -> frozenset:
        return frozenset(set(self.predicates) - set(self.predicate_dimensions))

    def federation_projections(self) -> list[dict]:
        """Versioned, inspectable local-predicate projections for manifests and audits."""
        return [{
            "profile_id": self.id,
            "profile_version": self.catalogue_version,
            "local_predicate": predicate,
            "federation_dimension": self.dimension_for(predicate),
            "mapping_relation": "narrower_than",
            "mapping_version": self.catalogue_version,
            "verification": "profile-declared",
        } for predicate in sorted(self.predicates)]

    def is_valid(self, axis: str, value: str) -> bool:
        """True iff ``value`` is a member of the closed set for ``axis``.

        ``axis`` is one of {predicate, modality, quantification, principle, canon,
        inference_rule}. Unknown axes return False.
        """
        sets = {
            "predicate": self.predicates,
            "modality": self.modalities,
            "quantification": self.quantifications,
            "principle": self.principles,
            "canon": self.canons,
            "inference_rule": self.inference_rules,
        }
        s = sets.get(axis)
        return value in s if s is not None else False


# ── registry ─────────────────────────────────────────────────────
PROFILES: dict[str, Profile] = {}


def register(profile: Profile) -> Profile:
    """Add a profile to the module-level registry, keyed by its id."""
    PROFILES[profile.id] = profile
    return profile


def get_profile(id: str) -> Profile:
    """Return the registered profile with this id (KeyError if not loaded)."""
    return PROFILES[id]
