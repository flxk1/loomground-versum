# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""The federation -> 5D rename: new names work, old names remain deprecated aliases.

Every alias kept for one release must return/accept the identical value as its new
counterpart and must warn ``DeprecationWarning`` on use. Loaders that previously
accepted a `federation_5d_version` JSON key must keep accepting it, alongside the
new `version_5d` key, with the new key winning when both are present.
"""
from __future__ import annotations

import json

import pytest

import versum.profiles  # noqa: F401 — register built-in profiles
from versum.identity.fingerprint import fingerprint
from versum.nd import NDRegistry, NDSystem, load_system
from versum.profile import get_profile


# ── Profile.projections_5d() / federation_projections() alias ──────────────

def test_projections_5d_is_the_new_name():
    profile = get_profile("generic")
    result = profile.projections_5d()
    assert isinstance(result, list) and result
    assert all("dimension_5d" in entry for entry in result)
    assert all("federation_dimension" not in entry for entry in result)


def test_federation_projections_alias_returns_identical_result_and_warns():
    profile = get_profile("generic")
    new_result = profile.projections_5d()
    with pytest.warns(DeprecationWarning):
        old_result = profile.federation_projections()
    assert old_result == new_result


# ── NDSystem.version_5d / federation_5d_version alias ───────────────────────

def _system_dict(version_key: str = "version_5d", extra: dict | None = None) -> dict:
    root = {
        "id": "alias-check", "namespace": "test.alias", "version": "1",
        version_key: "2",
        "axes": {"a": {"value_type": "string", "vocabulary_mode": "open"}},
    }
    if extra:
        root.update(extra)
    return {"nd_system": root}


def test_version_5d_is_the_new_field():
    system = NDSystem.from_dict(_system_dict("version_5d"))
    assert system.version_5d == "2"


def test_federation_5d_version_property_equals_version_5d_and_warns():
    system = NDSystem.from_dict(_system_dict("version_5d"))
    with pytest.warns(DeprecationWarning):
        old_value = system.federation_5d_version
    assert old_value == system.version_5d == "2"


def test_loader_accepts_old_federation_5d_version_key():
    system = NDSystem.from_dict(_system_dict("federation_5d_version"))
    assert system.version_5d == "2"


def test_loader_prefers_new_key_when_both_present():
    raw = _system_dict("version_5d")
    raw["nd_system"]["federation_5d_version"] = "99"
    system = NDSystem.from_dict(raw)
    assert system.version_5d == "2"  # version_5d wins


def test_old_key_input_round_trips_to_new_key_in_manifest():
    system = NDSystem.from_dict(_system_dict("federation_5d_version")).validate()
    reg = NDRegistry()
    reg.register(system)
    manifest = reg.manifest()
    entry = next(s for s in manifest["systems"] if s["id"] == "alias-check")
    assert entry["version_5d"] == "2"
    assert "federation_5d_version" not in entry


def test_load_system_from_file_accepts_old_key(tmp_path):
    p = tmp_path / "system.json"
    p.write_text(json.dumps(_system_dict("federation_5d_version")), encoding="utf-8")
    system = load_system(p)
    assert system.version_5d == "2"


# ── audit output key: dimension_5d (new only) ───────────────────────────────

def test_audit_output_uses_dimension_5d_key_only():
    profile = get_profile("generic")
    for entry in profile.projections_5d():
        assert "dimension_5d" in entry
        assert "federation_dimension" not in entry


# ── fingerprint key: dimensions_5d (new only) ───────────────────────────────

def test_fingerprint_uses_dimensions_5d_key_only():
    profile = get_profile("generic")
    fp = fingerprint("urn:test:1", [], profile)
    assert "dimensions_5d" in fp
    assert "federation_5d" not in fp


def test_old_fingerprint_key_is_read_under_its_new_name():
    from versum.identity.fingerprint import upgrade_fingerprint, upgrade_fingerprint_store

    old = {"federation_5d": {"causal": 2}, "form_profile": {}}
    assert upgrade_fingerprint(old) == {"dimensions_5d": {"causal": 2}, "form_profile": {}}
    both = {"federation_5d": {"causal": 1}, "dimensions_5d": {"causal": 9}}
    assert upgrade_fingerprint(both) == {"dimensions_5d": {"causal": 9}}
    assert upgrade_fingerprint_store({"urn:a": old})["urn:a"]["dimensions_5d"] == {"causal": 2}


def test_graph_version_is_the_same_for_an_old_key_fingerprints_store(tmp_path):
    from versum.snapshot import mint_graph_version
    from versum.sync import BY_DOMAIN

    domain = tmp_path / BY_DOMAIN / "law"
    domain.mkdir(parents=True)
    (domain / "claims.csv").write_text("claim_id,text\nc1,x\n", encoding="utf-8")
    store = domain / "fingerprints.json"
    store.write_text(json.dumps({"urn:a": {"dimensions_5d": {"causal": 1}}}), encoding="utf-8")
    current = mint_graph_version(tmp_path)
    store.write_text(json.dumps({"urn:a": {"federation_5d": {"causal": 1}}}), encoding="utf-8")
    assert mint_graph_version(tmp_path) == current


def test_ndsystem_accepts_the_old_keyword_with_a_warning():
    kwargs = dict(system_id="system:x", namespace="x", version="1", axes={})
    with pytest.deprecated_call():
        old = NDSystem(federation_5d_version="2", **kwargs)
    assert old.version_5d == "2"
    assert NDSystem(version_5d="2", **kwargs) == old
