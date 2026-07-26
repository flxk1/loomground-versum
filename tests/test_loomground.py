from __future__ import annotations

import pytest

from versum.loomground import canonical_observation, grammar_text, language_info, reasoning_request
from versum.nd import NDRegistry


def test_adapter_uses_authoritative_language_identity():
    info = language_info()
    request = reasoning_request("actor a\nmaster m", {"risk": "low"})
    assert info["language"] == request["language"] == "loomground"
    assert info["language_version"] == request["language_version"]
    assert info["grammar_sha256"] == request["grammar_sha256"]
    assert "loomground" in grammar_text().lower()
    assert request["transport"] == {"risk": "low"}


def test_nd_manifest_records_consumed_loomground_grammar():
    manifest = NDRegistry(include_core=True).manifest()
    assert manifest["grammar"]["language"] == "loomground"
    assert len(manifest["grammar"]["grammar_sha256"]) == 64


def test_canonical_observation_is_preserved_not_interpreted():
    value = {"nodes": [{"id": "a", "class": "actor"}], "cords": [],
             "reservations": [], "extension": {"host": "free"}}
    assert canonical_observation(value) == value


def test_observation_shape_is_checked_at_boundary():
    with pytest.raises(ValueError, match="cords"):
        canonical_observation({"nodes": [], "reservations": []})
