"""Governance plane fit: one 5D binding in the plane package, read at runtime (rules 1-3, 7).

The relation -> 5D map lives only in the governance kit's package data
(``loomground_governance/data/dimension-binding.json``); the versum adapter reads it and
keeps no copy. The plane is discoverable under ``loomground.planes`` and its nD system
validates through ``versum.nd`` at the language version.
"""
from __future__ import annotations

import ast
import importlib.metadata
import re
from pathlib import Path

import pytest

governance = pytest.importorskip("loomground_governance")
pytest.importorskip("loomground_governance.plane")

from versum import position5d as p5  # noqa: E402
from versum.dimensions import Dimension  # noqa: E402
from versum.integrations import loomground as integration  # noqa: E402
from versum.integrations.loomground import LoomgroundAdapter, loomground_mapping  # noqa: E402
from versum.nd import NDSystem  # noqa: E402
from versum.planes import DescriptorPlane  # noqa: E402

ADAPTER_SOURCE = Path(integration.__file__).with_name("adapter.py")


def _entry_point():
    eps = [ep for ep in importlib.metadata.entry_points(group="loomground.planes")
           if ep.name == "governance"]
    assert len(eps) == 1, "the governance plane entry point is not installed"
    return eps[0]


def test_adapter_mapping_equals_the_governance_data_file():
    document = governance.dimension_binding()
    mapping = LoomgroundAdapter().mapping()
    assert mapping.mapping_id == document["id"]
    assert mapping.version == document["version"]
    assert {name: (rel.dimension, rel.semantic_role)
            for name, rel in mapping.relations.items()} == {
        name: (spec["dimension"], spec["semantic_role"])
        for name, spec in document["relations"].items()}
    # the lazy module attribute is the same runtime read, not a copy
    assert integration.LOOMGROUND_MAPPING == mapping == loomground_mapping()


def test_no_literal_relation_to_dimension_map_left_in_the_adapter():
    source = ADAPTER_SOURCE.read_text(encoding="utf-8")
    strings = {node.value for node in ast.walk(ast.parse(source))
               if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert not strings & set(p5.DIMENSIONS), "a dimension name is spelled in adapter.py"
    assert "dimension" not in strings, "a {relation: {'dimension': ...}} literal remains"
    for relation in governance.dimension_binding()["relations"]:
        assert not re.search(rf'"{relation}"\s*:\s*\{{', source), relation


def test_binding_names_only_the_five_dimensions():
    descriptor = _entry_point().load()()
    assert descriptor["binding"]
    assert set(descriptor["binding"].values()) <= set(p5.DIMENSIONS)
    for relation in LoomgroundAdapter().mapping().relations.values():
        Dimension(relation.dimension)  # raises on a sixth dimension
    projection = LoomgroundAdapter().import_observation({
        "nodes": [{"id": "a", "class": "actor"}, {"id": "g", "class": "gate"},
                  {"id": "master", "class": "master"}],
        "cords": [{"from": "a", "to": "g", "type": "authority"},
                  {"from": "g", "to": "master", "type": "egress"}],
        "reservations": [{"kind": "k", "by": "legal"}],
    })
    assert {r.dimension for r in projection.relations} <= set(p5.DIMENSIONS)


def test_entry_point_is_discoverable_and_its_nd_system_validates():
    ep = _entry_point()
    assert ep.value == "loomground_governance.plane:plane"
    raw = ep.load()()
    assert raw["plane"] == "governance"
    assert raw["language_version"] == governance.language_version()
    system = NDSystem.from_dict(dict(raw["nd_system"])).validate()
    assert system.version == raw["language_version"]
    assert system.unknown_values == "reject"
    plane = DescriptorPlane.from_descriptor(raw, entry_name="governance")
    assert plane.plane_id == "governance"
    assert dict(plane.binding()) == raw["binding"]


def test_adapter_nd_system_is_the_planes_own_with_policy_ladders():
    plane_axes = governance.plane_descriptor()["nd_system"]["axes"]
    adapter_system = LoomgroundAdapter().nd_systems()[0]
    assert set(adapter_system.axes) == set(plane_axes)
    for axis_id, spec in plane_axes.items():
        assert list(adapter_system.axes[axis_id].vocabulary) == list(spec.get("vocabulary", []))
    assert adapter_system.version.startswith(governance.language_version() + "+")


def test_loomground_names_only_in_the_new_plane_surfaces():
    assert governance.dimension_binding()["id"] == "loomground-governance-5d"
    assert LoomgroundAdapter().artifacts().metadata["mapping_id"] == "loomground-governance-5d"
    raw = governance.plane_descriptor()
    assert raw["nd_system"]["id"] == "loomground-governance"
    assert raw["nd_system"]["namespace"] == "loomground"
    assert not [k for k in raw["nd_system"] if "5d" in k.lower()]


def test_delegator_declared_later_keeps_its_class():
    projection = LoomgroundAdapter().import_observation({
        "nodes": [{"id": "helper", "class": "actor", "on_behalf_of": "lead"},
                  {"id": "lead", "class": "actor", "party": "firm"},
                  {"id": "g", "class": "gate"}, {"id": "master", "class": "master"}],
        "cords": [{"from": "helper", "to": "g", "type": "authority"},
                  {"from": "g", "to": "master", "type": "egress"}],
        "reservations": [],
    })
    nodes = {n.node_id: n for n in projection.nodes}
    assert nodes["lead"].node_type == "actor"
    assert nodes["lead"].attributes == {"id": "lead", "class": "actor", "party": "firm"}
    delegation = [r for r in projection.relations if r.local_predicate == "on_behalf_of"]
    assert [(r.source_id, r.target_id) for r in delegation] == [("helper", "lead")]
