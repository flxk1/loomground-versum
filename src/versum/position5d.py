"""The five-value 5D position of a versum entry, and its one dominant dimension.

Every entry carries a *position*: one value on each of the five dimensions (structural,
causal, intentional, temporal, relational). The position is computed deterministically
from the entry's typed relations and the installed planes' bindings (no neural
vectoriser):

* each plane claim on the entry contributes 1 to the dimension its plane binds the
  claim's ``relation`` to;
* each coordinate field of that claim whose axis id the plane binds contributes 1 to that
  dimension.

The five values are the contributions normalised to sum to 1 (rounded to six places), so
positions of entries with different numbers of claims are comparable. An entry that no
plane contributes to (no plane claimed its sentence, or no claim touched a bound relation
or field) gets the all-zero position, basis ``"default"``, and the default dominant
dimension ``relational`` (``dimensions.DEFAULT_DIMENSION``).

The dominant dimension is the argmax of the raw contributions. Ties are broken by the
fixed order of :data:`TIE_ORDER` (the declaration order of ``dimensions.Dimension``):
structural, causal, intentional, temporal, relational — the earliest wins.
"""
from __future__ import annotations

from collections.abc import Mapping

from .dimensions import DEFAULT_DIMENSION, Dimension

#: The five dimensions, in their canonical (and tie-breaking) order.
DIMENSIONS: tuple[str, ...] = tuple(d.value for d in Dimension)
TIE_ORDER: tuple[str, ...] = DIMENSIONS
#: The dominant dimension of an entry with no plane contribution.
NO_PLANE_DOMINANT: str = DEFAULT_DIMENSION.value
BASIS_PLANES = "planes"
BASIS_DEFAULT = "default"
_PLACES = 6


def is_dimension(value) -> bool:
    return isinstance(value, str) and value in DIMENSIONS


def zero_contributions() -> dict[str, int]:
    return {d: 0 for d in DIMENSIONS}


def position(contributions: Mapping[str, float]) -> dict[str, float]:
    """The normalised five-value position; all zeros when nothing contributed."""
    unknown = set(contributions) - set(DIMENSIONS)
    if unknown:
        raise ValueError(f"not a 5D dimension: {sorted(unknown)!r}")
    raw = {d: float(contributions.get(d, 0) or 0) for d in DIMENSIONS}
    if any(v < 0 for v in raw.values()):
        raise ValueError("5D contributions must be non-negative")
    total = sum(raw.values())
    if total == 0:
        return {d: 0.0 for d in DIMENSIONS}
    return {d: round(raw[d] / total, _PLACES) for d in DIMENSIONS}


def dominant(contributions: Mapping[str, float]) -> str:
    """Exactly one dominant dimension: argmax, ties broken by :data:`TIE_ORDER`."""
    best, best_value = NO_PLANE_DOMINANT, 0.0
    for d in TIE_ORDER:
        v = float(contributions.get(d, 0) or 0)
        if v > best_value:
            best, best_value = d, v
    return best


def basis(contributions: Mapping[str, float]) -> str:
    return BASIS_PLANES if any(float(v or 0) > 0 for v in contributions.values()) \
        else BASIS_DEFAULT
