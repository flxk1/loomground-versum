"""versum/model.py — the rails for any model plugged into the engine.

The engine is model-agnostic: it ships no model and names no provider. It defines only
the CONTRACT a plugged-in model must honour on the *grounded path* — the tasks whose
output enters the graph (identity resolution, span typing, concept merge, domain
classification), where a wrong or drifting answer would corrupt it.

The contract is **deterministic + constrained**. Grounded-path calls must use temperature
0 and a constrained output format (the literal ``"json"`` or an explicit JSON schema), so
the answer is reproducible and cannot fall outside the closed vocabulary.
``validate_decoding`` enforces it; adapters — which live OUTSIDE this package (an
optional install extra; see docs/architecture/adapter-contract.md) — call it before every request and
default to it.

Temperature is the weakest of the three guarantees: it buys reproducibility. The
constrained format makes an off-vocabulary answer impossible, and verification of the
returned value against the closed catalogue happens at the call site regardless. Low
temperature, a grammar, and a check — in that order of strength.
"""
from __future__ import annotations

# Tasks whose output enters the graph — must be deterministic + constrained.
GROUNDED_TASKS = frozenset({"resolve", "type_span", "judge_merge", "classify_domain"})

# A constrained format is the literal "json" or an explicit schema object (a dict).
_LITERAL_CONSTRAINED = frozenset({"json"})


def _is_constrained(fmt) -> bool:
    # a dict is an explicit JSON schema; check it first (dicts are unhashable, so
    # `fmt in <set>` would raise). Otherwise accept the literal "json".
    return isinstance(fmt, dict) or (isinstance(fmt, str) and fmt in _LITERAL_CONSTRAINED)


def validate_decoding(task: str, config: dict) -> None:
    """Raise ``ValueError`` if a grounded-path task is configured non-deterministically.

    Grounded tasks (``GROUNDED_TASKS``) require ``temperature == 0`` and a constrained
    output ``format``. Non-grounded tasks are unconstrained. An adapter must call this
    before every grounded request; a config that ships a non-zero temperature on the
    grounded path fails here rather than silently corrupting the graph.
    """
    if task not in GROUNDED_TASKS:
        return
    temp = config.get("temperature", None)
    if temp != 0:
        raise ValueError(
            f"grounded task {task!r} requires temperature 0, got {temp!r}")
    if not _is_constrained(config.get("format")):
        raise ValueError(
            f"grounded task {task!r} requires a constrained format "
            f'("json" or a JSON schema object), got {config.get("format")!r}')
