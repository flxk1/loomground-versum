"""Mutation probe for decision D1's hard invariant: the deontic plane's binding() is
ALWAYS ``{}`` — an operator (O/P/F) is OUGHT, not a fact on the 5D manifold — and the
generic plane-binding contribution code in ``versum.planes`` (``if relation in bind:
c[bind[relation]] += 1``) must fail closed, not silently apply, if that were ever to
change.

This is injected through the REAL plane pipeline (a descriptor fixture built from the
*real* installed deontic plane, with only its ``binding()`` mutated, then run through
``versum.planes.load_planes`` / ``build_source_entries`` and, separately, a real
``loomground.planes`` entry point discovered by ``versum index`` end to end) — never a
post-import monkeypatch of the consumer (``versum.planes`` itself is untouched).

Revert probe: each assertion below is inside a ``pytest.raises`` block. If the guard in
``versum.planes`` (the ``if pid == "deontic" and bind: raise ...`` check next to
``bind = plane.binding()``) were removed or weakened, the mutated ``{'O': 'causal'}``
binding would flow straight through the generic ``if relation in bind: c[bind[relation]]
+= 1`` line, no exception would be raised, and these tests would fail with "DID NOT
RAISE" — so a passing run here is real evidence the guard exists and does the work.
"""
from __future__ import annotations

import copy
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

import pytest

from versum import planes as pl

import deontic  # noqa: E402 — the real deontic package; a hard dependency

REPO = Path(__file__).resolve().parents[1]
MUTATED_BINDING = {"O": "causal"}  # the injected, contract-breaching binding


def _real_deontic_descriptor() -> dict:
    eps = [e for e in importlib.metadata.entry_points(group=pl.ENTRY_POINT_GROUP)
           if e.name == "deontic"]
    assert eps, "the deontic plane is not installed in this venv"
    return eps[0].load()()


# Fetched once, at import time — BEFORE any test monkeypatches
# ``importlib.metadata.entry_points`` to install the fake single-entry-point view used by
# the end-to-end test below. ``_mutated_deontic_descriptor`` (itself loaded as that fake
# entry point's target) must never re-query entry-point discovery at call time: under the
# monkeypatched view discovery would find only the fake "deontic" entry again and load
# this very function a second time — infinite recursion, not a real deontic plane.
_REAL_DEONTIC_RAW = _real_deontic_descriptor()


def _mutated_deontic_descriptor() -> dict:
    """The real deontic plane descriptor, with ONLY ``binding()`` replaced by a
    non-empty, out-of-contract operator binding. Everything else (``produce``,
    ``nd_system``, ``language_version``) is the real, installed plane's own (captured at
    import time, see ``_REAL_DEONTIC_RAW``) — this is not a fake plane invented for the
    test, it is the real one with one field mutated."""
    raw = dict(_REAL_DEONTIC_RAW)
    raw["binding"] = dict(MUTATED_BINDING)
    return raw


# A sentence the real deontic prose extractor actually claims with relation "O", so the
# mutated binding's key really is hit by the generic contribution code if nothing stops it.
OBLIGATION_SENTENCE = "A processor shall notify the authority."


def test_mutated_binding_is_real_and_non_empty():
    # Prove the injection is live before proving the refusal: this is not a no-op fixture.
    mutated = pl.DescriptorPlane.from_descriptor(_mutated_deontic_descriptor())
    assert mutated.binding() == MUTATED_BINDING
    real = pl.DescriptorPlane.from_descriptor(_real_deontic_descriptor())
    assert real.binding() == {}


def test_the_sentence_really_produces_an_o_relation_claim():
    real = pl.DescriptorPlane.from_descriptor(_real_deontic_descriptor())
    claims = real.produce(OBLIGATION_SENTENCE)
    assert claims and claims[0]["relation"] == "O"


def test_build_source_entries_fails_closed_on_a_non_empty_deontic_binding():
    mutated = pl.load_planes([_mutated_deontic_descriptor()])
    with pytest.raises(pl.PlaneIndexError, match="deontic"):
        pl.build_source_entries(OBLIGATION_SENTENCE, "urn:mutation-probe:1", mutated)


def test_versum_index_fails_closed_end_to_end_through_a_fake_entry_point(
        tmp_path, monkeypatch, capsys):
    """The same mutation, but through a fake INSTALLED entry point discovered by the real
    ``versum index`` CLI (``main()``), not a direct descriptor list — the closest a test
    can get to the real ``loomground.planes`` discovery path without editing an installed
    distribution's metadata."""
    from versum.__main__ import main

    fake = importlib.metadata.EntryPoint(
        name="deontic", value=f"{__name__}:_mutated_deontic_descriptor",
        group=pl.ENTRY_POINT_GROUP)
    real_eps = importlib.metadata.entry_points

    def entry_points(**kw):
        if kw.get("group") == pl.ENTRY_POINT_GROUP:
            return importlib.metadata.EntryPoints([fake])
        return real_eps(**kw)

    monkeypatch.setattr(importlib.metadata, "entry_points", entry_points)

    src = tmp_path / "src"
    src.mkdir()
    (src / "norm.txt").write_text(OBLIGATION_SENTENCE + "\n", encoding="utf-8")
    out = tmp_path / "out"
    assert REPO not in out.resolve().parents  # scratch only, never in-tree

    rc = main(["index", str(src), "--out", str(out)])
    err = capsys.readouterr().err
    assert rc != 0
    report = json.loads(err.strip().splitlines()[-1])
    assert report["status"] == "error"
    assert report["plane"] == "deontic"
    assert not out.exists(), "a failed run must write nothing"
