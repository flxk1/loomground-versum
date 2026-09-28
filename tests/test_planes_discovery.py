"""Plane discovery (entry-point group ``loomground.planes``) and descriptor validation.

Uses the FAKE plane under ``tests/fixtures/planes_fake`` — no real plane is required.
"""
from __future__ import annotations

import csv
import importlib
import importlib.metadata
import json
from pathlib import Path

import pytest

from versum import planes as pl
from versum.__main__ import main

FIXTURES = Path(__file__).parent / "fixtures" / "planes_fake"


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURES))
    import fake_plane
    return importlib.reload(fake_plane)


def _eps(monkeypatch, *pairs):
    """Make importlib.metadata report exactly these (name, value) plane entry points."""
    eps = [importlib.metadata.EntryPoint(name=n, value=v, group=pl.ENTRY_POINT_GROUP)
           for n, v in pairs]
    real = importlib.metadata.entry_points

    def entry_points(**kw):
        if kw.get("group") == pl.ENTRY_POINT_GROUP:
            return importlib.metadata.EntryPoints(eps)
        return real(**kw)

    monkeypatch.setattr(importlib.metadata, "entry_points", entry_points)


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_discover_planes_finds_registered_entry_point(fake, monkeypatch):
    _eps(monkeypatch, ("fakeplane", "fake_plane:plane"))
    found = pl.discover_planes()
    assert [p.plane_id for p in found] == ["fakeplane"]
    plane = found[0]
    assert isinstance(plane, pl.PlaneAdapter)
    assert plane.language_version == "0.0.1-test"
    assert plane.nd_system().version == plane.language_version
    assert plane.nd_system().system_id == "fakeplane-system"
    assert dict(plane.binding()) == fake.BINDING


def test_versum_index_cli_invokes_discovered_plane_without_flags(fake, monkeypatch, tmp_path):
    _eps(monkeypatch, ("fakeplane", "fake_plane:plane"))
    calls = []
    original = fake.produce

    def counting(sentence, context=None):
        calls.append(sentence)
        return original(sentence, context)

    monkeypatch.setattr(fake, "produce", counting)
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "a.txt").write_text("Ann shouts at noon. Bob naps.\n", encoding="utf-8")

    assert main(["index", str(folder)]) == 0          # no plane flag of any kind
    # the producer ran on every sentence of the source (plane() also runs it for examples)
    assert calls[-2:] == ["Ann shouts at noon.", "Bob naps."]
    v = folder / ".versum"
    manifest = json.loads((v / "index.json").read_text())
    assert manifest["planes"] == [{"plane": "fakeplane", "language_version": "0.0.1-test",
                                   "system_id": "fakeplane-system"}]
    systems = json.loads((v / "nd" / "systems.json").read_text())
    assert "fakeplane-system" in {s["id"] for s in systems["systems"]}
    rows = [r for r in _rows(v / "nd" / "assignments.csv")
            if r["system_id"] == "fakeplane-system"]
    assert rows and json.loads(rows[0]["value"]) == "loud"


def test_entry_name_must_equal_plane_id(fake, monkeypatch):
    _eps(monkeypatch, ("other", "fake_plane:plane"))
    with pytest.raises(pl.PlaneDescriptorError, match="entry-point name"):
        pl.discover_planes()


def test_entry_point_that_fails_to_load_fails_closed(monkeypatch):
    _eps(monkeypatch, ("ghost", "no_such_plane_module_xyz:plane"))
    with pytest.raises(pl.PlaneDescriptorError, match="failed to load"):
        pl.discover_planes()


def test_cli_exits_non_zero_on_broken_plane(monkeypatch, tmp_path):
    _eps(monkeypatch, ("ghost", "no_such_plane_module_xyz:plane"))
    (tmp_path / "a.txt").write_text("Ann naps.\n", encoding="utf-8")
    assert main(["index", str(tmp_path)]) != 0
    assert not (tmp_path / ".versum").exists()


def test_injection_seam_replaces_discovery(fake, monkeypatch):
    _eps(monkeypatch)                                   # nothing installed
    assert pl.discover_planes() == []
    assert [p.plane_id for p in pl.discover_planes([fake.plane])] == ["fakeplane"]
    assert [p.plane_id for p in pl.discover_planes([fake.plane()])] == ["fakeplane"]


@pytest.mark.parametrize("mutate, match", [
    (lambda d: d.update(language_version="9.9"), "language_version"),
    (lambda d: d["binding"].update(shouts="contextual"), "five dimensions"),
    (lambda d: d["binding"].update(tone="Causal"), "five dimensions"),
    (lambda d: d["nd_system"].pop("axes"), "does not validate"),
    (lambda d: d["nd_system"]["axes"]["tone"].update(vocabulary=[]), "does not validate"),
    (lambda d: d["nd_system"]["bindings"][0].update(allowed_axes=["nope"]),
     "does not validate"),
    (lambda d: d["nd_system"]["validation"].update(unknown_values="accept"), "reject"),
    (lambda d: d.pop("produce"), "lacks"),
    (lambda d: d.update(produce="not callable"), "not callable"),
    (lambda d: d.update(plane="bad id!"), "invalid plane id"),
    (lambda d: d.update(examples=[{"sentence": 1}]), "examples"),
])
def test_invalid_descriptor_fails_closed(fake, mutate, match):
    d = fake.plane()
    mutate(d)
    with pytest.raises(pl.PlaneDescriptorError, match=match):
        pl.load_planes([d])


def test_duplicate_plane_id_fails_closed(fake):
    with pytest.raises(pl.PlaneDescriptorError, match="more than once"):
        pl.load_planes([fake.plane(), fake.plane()])


def test_descriptor_callable_that_raises_fails_closed():
    def boom():
        raise RuntimeError("no")
    with pytest.raises(pl.PlaneDescriptorError, match="raised RuntimeError"):
        pl.load_planes([boom])


def test_plane_omitting_the_5d_version_key_is_accepted(fake):
    d = fake.plane()
    assert not any(k.endswith("5d_version") for k in d["nd_system"])
    assert pl.load_planes([d])[0].nd_system().validate()
