"""The deontic plane as the versum reads it: entry-point discovery, the descriptor
contract, and rule 1 (the nD system is the plane's published document)."""
from __future__ import annotations

import importlib.metadata
import json

import pytest

from versum import planes as pl
from versum import position5d as p5
from versum.deontic import (deontic_binding, deontic_nd_system, deontic_plane,
                            register_deontic)
from versum.nd import NDRegistry, NDSystem

import deontic  # noqa: E402 — a hard dependency; never skipped


def _published_document() -> dict:
    return json.loads(deontic.artifact_path("nd-system.json").read_text(encoding="utf-8"))


def test_deontic_entry_point_is_discoverable():
    eps = [ep for ep in importlib.metadata.entry_points(group=pl.ENTRY_POINT_GROUP)
           if ep.name == "deontic"]
    assert len(eps) == 1
    raw = eps[0].load()()
    plane = pl.DescriptorPlane.from_descriptor(raw, entry_name="deontic")
    assert plane.plane_id == "deontic"


def test_nd_system_validates_via_versum_nd_with_version_equal_language_version():
    raw = deontic_plane()
    doc = _published_document()
    system = NDSystem.from_dict(doc).validate()
    assert system.version == raw.language_version == deontic.language_version()
    assert system.unknown_values == "reject"
    assert not [k for k in doc if "5d" in k.lower()]  # the plane omits the 5D version key


def test_rule1_deontic_nd_system_equals_the_published_document():
    assert deontic_nd_system() == NDSystem.from_dict(_published_document()).validate()
    assert deontic_nd_system() == deontic_plane().nd_system()
    # the vocabulary comes from the pack, not from the versum
    assert list(deontic_nd_system().axes["operator"].vocabulary) == \
        list(deontic.VALID_OPERATORS)
    assert list(deontic_nd_system().axes["incident"].vocabulary) == list(deontic.INCIDENTS)


def test_register_deontic_keeps_its_signature():
    reg = NDRegistry()
    system = register_deontic(reg)
    assert system.system_id == "loomground-deontic"
    assert system.version == deontic.language_version()


def test_binding_names_only_the_five_dimensions():
    # Round 4 correction to D1: operators (O/P/F) are OUGHT, not IS, so none of them binds
    # to a 5D dimension; the binding is always empty. A norm's content enters 5D only
    # through the factual plane (see versum.planes, the spans.content -> factual bridge,
    # and docs/architecture/planes.md).
    b = deontic_binding()
    assert b == {}
    assert all(p5.is_dimension(v) for v in b.values())  # vacuously true on an empty binding
