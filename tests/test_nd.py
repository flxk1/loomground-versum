import json

import pytest

from versum.nd import (Binding, CoordinateAssignment, NDRegistry, NDSystem, Primitive, Truth,
                       load_assignments, load_bindings, load_system, save_assignments,
                       save_bindings, required_binding_gaps, scope_compatibility,
                       select_by_scope)


SYSTEM = {
    "nd_system": {
        "id": "constrained-optimization",
        "namespace": "math.optimization",
        "version": "1.0.0",
        "federation_5d_version": "1",
        "axes": {
            "variable_space": {
                "value_type": "controlled_identifier", "cardinality": "one",
                "vocabulary": ["real", "integer", "binary"],
                "primitives": ["equal", "contains"],
            },
            "dimensionality": {
                "value_type": "non_negative_integer", "cardinality": "one",
                "primitives": ["equal", "precedes"],
            },
        },
        "bindings": [{"form_slot": "quantification.range",
                      "allowed_axes": ["variable_space"], "required": True}],
        "ontology_relations": [
            {"axis": "variable_space", "left": "real", "relation": "contains",
             "right": "binary"}
        ],
        "validation": {"provenance_required": True},
    }
}


def test_user_nd_system_loads_and_namespaces_axes(tmp_path):
    p = tmp_path / "system.json"
    p.write_text(json.dumps(SYSTEM))
    system = load_system(p)
    assert system.qualified_axis("variable_space") == \
        "math.optimization:variable_space"
    assert system.relation("variable_space", "real", "binary", Primitive.CONTAINS) \
        == Truth.TRUE
    assert system.relation("variable_space", "binary", "real", "contained_by") \
        == Truth.TRUE
    assert system.relation("dimensionality", 2, 3, "precedes") == Truth.UNKNOWN


def test_coordinate_assignment_is_typed_and_provenance_bearing():
    system = NDSystem.from_dict(SYSTEM).validate()
    valid = CoordinateAssignment(
        "claim:1", system.system_id, system.version, "variable_space", "real",
        "source:span:1", "source-explicit")
    assert valid.violations(system) == []
    bad = CoordinateAssignment(
        "claim:1", system.system_id, system.version, "dimensionality", -1, "", "")
    errors = bad.violations(system)
    assert any("provenance" in e for e in errors)
    assert any("non-negative" in e for e in errors)


def test_binding_must_follow_declared_slot_axis_contract():
    system = NDSystem.from_dict(SYSTEM).validate()
    valid = Binding("claim:1", "quantification.range", "range", "coord:1",
                    "variable_space", "real", "source:span:1", "curated")
    assert valid.violations(system) == []
    invalid = Binding("claim:1", "quantification.range", "range", "coord:2",
                      "dimensionality", 3, "source:span:1", "curated")
    assert any("not allowed" in e for e in invalid.violations(system))


def test_closed_vocabulary_rejects_unknown_value():
    system = NDSystem.from_dict(SYSTEM).validate()
    a = CoordinateAssignment("c", system.system_id, system.version,
                             "variable_space", "complex", "s", "manual")
    assert any("closed vocabulary" in e for e in a.violations(system))


def test_invalid_system_is_rejected():
    raw = {"id": "x", "namespace": "x", "version": "1", "axes": {
        "a": {"value_type": "mystery", "primitives": ["magic"]}}}
    with pytest.raises(ValueError):
        NDSystem.from_dict(raw).validate()


def test_assignments_and_bindings_round_trip_typed_values(tmp_path):
    assignments = [{"assignment_id": "a1", "subject_id": "c1", "system_id": "chem",
                    "system_version": "1", "axis_id": "temperature",
                    "value": {"amount": 80, "unit": "degC"}, "source_id": "span:1",
                    "method": "source-explicit", "verification": "candidate"}]
    bindings = [{"binding_id": "b1", "claim_id": "c1", "form_slot": "predicate.agent",
                 "semantic_role": "agent", "assignment_id": "a1", "axis_id": "actor",
                 "value": ["controller"], "source_id": "span:1", "method": "curated",
                 "verification": "confirmed"}]
    save_assignments(tmp_path / "assignments.csv", assignments)
    save_bindings(tmp_path / "bindings.csv", bindings)
    assert load_assignments(tmp_path / "assignments.csv")[0]["value"]["amount"] == 80
    assert load_bindings(tmp_path / "bindings.csv")[0]["value"] == ["controller"]


def test_registry_allows_independent_namespaces():
    a = NDSystem.from_dict(SYSTEM).validate()
    other_raw = {"id": "other", "namespace": "other.math", "version": "1",
                 "axes": {"variable_space": {"value_type": "string"}}}
    b = NDSystem.from_dict(other_raw).validate()
    registry = NDRegistry()
    registry.register(a); registry.register(b)
    assert len(registry.axes) == 3


def test_folder_index_registers_user_nd_system(tmp_path):
    from versum.store.index import index_folder
    cfg = tmp_path / "math.json"
    cfg.write_text(json.dumps(SYSTEM))
    docs = tmp_path / "docs"; docs.mkdir()
    (docs / "claim.txt").write_text("Heat causes expansion in every sample.")
    result = index_folder(docs, nd_system_paths=[cfg])
    assert result["n_nd_systems"] == 2
    manifest = json.loads((docs / ".versum" / "nd" / "systems.json").read_text())
    assert {s["id"] for s in manifest["systems"]} == {
        "constrained-optimization", "versum-context"}


def test_required_binding_gap_is_diagnostic_not_claim_rejection():
    system = NDSystem.from_dict(SYSTEM).validate()
    gaps = required_binding_gaps(["c1"], system, [])
    assert gaps == [{"claim_id": "c1", "form_slot": "quantification.range",
                     "diagnostic": "contextually-incomplete",
                     "allowed_axes": ["variable_space"]}]


def test_scope_compatibility_is_derived_and_explained():
    system = NDSystem.from_dict(SYSTEM).validate()
    same = scope_compatibility(system, {"variable_space": ["real"]},
                               {"variable_space": ["real"]})
    assert same["result"] == "true"
    unknown = scope_compatibility(system, {"dimensionality": [2]},
                                  {"dimensionality": [3]})
    assert unknown["result"] == "unknown"


def test_contextual_selection_preserves_unknown_separately():
    system = NDSystem.from_dict(SYSTEM).validate()
    out = select_by_scope(system, {
        "c1": {"variable_space": ["real"]},
        "c2": {"dimensionality": [2]},
    }, {"variable_space": ["real"]})
    assert out["selected"] == ["c1"]
    assert out["unknown"] == ["c2"]
    assert out["excluded"] == []
