"""The decoding policy: grounded-path model calls must be deterministic + constrained,
and the engine must name no model provider.
"""
from pathlib import Path

import pytest

from versum import model


def test_grounded_rejects_nonzero_temperature():
    for task in model.GROUNDED_TASKS:
        with pytest.raises(ValueError):
            model.validate_decoding(task, {"temperature": 0.7, "format": "json"})


def test_grounded_rejects_unconstrained_format():
    with pytest.raises(ValueError):
        model.validate_decoding("resolve", {"temperature": 0})            # no format
    with pytest.raises(ValueError):
        model.validate_decoding("resolve", {"temperature": 0, "format": "text"})


def test_grounded_accepts_temp0_and_constrained():
    model.validate_decoding("resolve", {"temperature": 0, "format": "json"})
    model.validate_decoding("judge_merge",
                            {"temperature": 0, "format": {"type": "object"}})


def test_nongrounded_task_is_unconstrained():
    # a non-grounded task (not in GROUNDED_TASKS) may use any settings
    model.validate_decoding("summarize", {"temperature": 0.9})


def test_engine_names_no_model_provider():
    src = (Path(__file__).resolve().parent.parent / "src" / "versum" / "model.py").read_text().lower()
    for p in ("ollama", "openai", "qwen", "phi", "llama", "anthropic", "gpt",
              "claude", "mistral", "gemini"):
        assert p not in src, f"engine model.py must not name provider {p!r}"
