"""More decoding-policy coverage — the grounded-path determinism contract.

Complements the core model-policy tests: the missing-temperature case (a default must NOT
be silently treated as 0) and per-task enumeration of GROUNDED_TASKS.
"""
import pytest

from versum import model


def test_missing_temperature_key_raises():
    # temperature key entirely absent -> must raise, not default to 0
    with pytest.raises(ValueError):
        model.validate_decoding("resolve", {"format": "json"})


def test_every_grounded_task_rejects_nonzero_temperature():
    for task in model.GROUNDED_TASKS:
        with pytest.raises(ValueError):
            model.validate_decoding(task, {"temperature": 0.2, "format": "json"})


def test_every_grounded_task_accepts_temp0_and_constrained():
    for task in model.GROUNDED_TASKS:
        # literal "json"
        model.validate_decoding(task, {"temperature": 0, "format": "json"})
        # explicit schema object
        model.validate_decoding(task, {"temperature": 0, "format": {"type": "object"}})


def test_nongrounded_task_always_accepted():
    # names not in GROUNDED_TASKS are unconstrained, whatever the config
    for cfg in ({"temperature": 1.7}, {}, {"temperature": 0.5, "format": "text"}):
        model.validate_decoding("summarize", cfg)
        model.validate_decoding("not_a_grounded_task", cfg)
