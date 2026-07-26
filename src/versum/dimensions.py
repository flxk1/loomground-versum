"""Federation-5D edge dimensions and composition algebra.

The five string values and composition table are the cross-project interoperability
contract.  Keep them stable.  Versum profiles map local predicates to these dimensions;
the local predicate remains available as the finer, profile-specific description.
"""
from __future__ import annotations

from enum import Enum


class Dimension(str, Enum):
    STRUCTURAL = "structural"
    CAUSAL = "causal"
    INTENTIONAL = "intentional"
    TEMPORAL = "temporal"
    RELATIONAL = "relational"


DEFAULT_DIMENSION = Dimension.RELATIONAL

_S = Dimension.STRUCTURAL
_C = Dimension.CAUSAL
_I = Dimension.INTENTIONAL
_T = Dimension.TEMPORAL
_R = Dimension.RELATIONAL

COMPOSITION_TABLE: dict[tuple[Dimension, Dimension], Dimension] = {
    (_S, _S): _S, (_S, _C): _C, (_S, _I): _I, (_S, _T): _T, (_S, _R): _S,
    (_C, _S): _C, (_C, _C): _C, (_C, _I): _I, (_C, _T): _T, (_C, _R): _C,
    (_I, _S): _S, (_I, _C): _C, (_I, _I): _I, (_I, _T): _T, (_I, _R): _I,
    (_T, _S): _S, (_T, _C): _C, (_T, _I): _I, (_T, _T): _T, (_T, _R): _T,
    (_R, _S): _S, (_R, _C): _C, (_R, _I): _I, (_R, _T): _T, (_R, _R): _R,
}


def compose(a: Dimension | str, b: Dimension | str) -> Dimension:
    """Return the dimension governing traversal across ``a`` followed by ``b``."""
    return COMPOSITION_TABLE[(Dimension(a), Dimension(b))]


def compose_weights(w1: float, w2: float) -> float:
    """Compose edge confidences multiplicatively."""
    return w1 * w2


def dimension_values() -> frozenset[str]:
    return frozenset(d.value for d in Dimension)
