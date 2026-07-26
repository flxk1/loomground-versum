from __future__ import annotations

import json

from versum.adapters import SystemAdapter, save_projection
from versum.__main__ import main
from versum.store.graph import check_edge_contracts, load_edges
from versum.nd import load_assignments, load_bindings
from versum.integrations.loomground import LoomgroundAdapter
from versum.nd import Primitive, Truth


OBSERVATION = {
    "nodes": [
        {"id": "agent", "class": "actor", "grade": "L2", "party": "publisher"},
        {"id": "review", "class": "gate", "risk_floor": "high",
         "grade_required": "L1"},
        {"id": "master", "class": "master"},
    ],
    "cords": [
        {"from": "agent", "to": "review", "type": "authority"},
        {"from": "review", "to": "master", "type": "egress"},
    ],
    "reservations": [
        {"kind": "publish", "by": "editor", "duration": "2h", "on_elapse": "halt"},
    ],
    "redress": [
        {"kind": "publish", "by": "ombud", "overturn": True, "within": "7d"},
    ],
}


def test_loomground_adapter_conforms_to_universal_protocol():
    adapter = LoomgroundAdapter()
    assert isinstance(adapter, SystemAdapter)
    assert adapter.identity().system_id == "loomground-governance"
    assert len(adapter.identity().grammar_sha256) == 64
    assert adapter.capabilities().semantic_projection
    assert not adapter.capabilities().parsing


def test_artifacts_generate_versioned_policy_sensitive_nd_system():
    default = LoomgroundAdapter().nd_systems()[0]
    custom = LoomgroundAdapter(policy={
        "risk_levels": ["minor", "major"],
        "grade_levels": ["manual", "assisted", "automatic"],
    }).nd_systems()[0]
    assert default.namespace == "loomground"
    assert default.axes["node_class"].vocabulary == ("actor", "human", "gate", "master")
    assert custom.axes["risk"].vocabulary == ("minor", "major")
    assert custom.axes["grade"].vocabulary == ("manual", "assisted", "automatic")
    assert custom.version != default.version
    assert custom.relation("grade", "manual", "automatic", Primitive.PRECEDES) == Truth.TRUE


def test_observation_projects_to_5d_graph_and_nd_assignments():
    projection = LoomgroundAdapter().import_observation(OBSERVATION)
    assert not projection.violations()
    nodes = {node.node_id: node for node in projection.nodes}
    assert nodes["agent"].node_type == "actor"
    assert nodes["review"].node_type == "gate"
    relations = {relation.local_predicate: relation for relation in projection.relations}
    assert relations["authority"].dimension == "intentional"
    assert relations["egress"].dimension == "causal"
    assert relations["reservation"].dimension == "intentional"
    assert relations["redress"].dimension == "intentional"
    coordinates = {(row.subject_id, row.axis_id, row.value) for row in projection.assignments}
    assert ("agent", "grade", "L2") in coordinates
    assert ("agent", "party", "publisher") in coordinates
    assert ("review", "risk", "high") in coordinates
    assert any(axis == "cord_type" and value == "authority"
               for _, axis, value in coordinates)


def test_claim_slots_bind_to_projected_coordinates():
    projection = LoomgroundAdapter().import_observation(OBSERVATION, claim_bindings=[{
        "claim_id": "claim-1", "subject_id": "agent", "axis_id": "party",
        "form_slot": "predicate.agent", "semantic_role": "responsible-party",
    }])
    assert len(projection.bindings) == 1
    binding = projection.bindings[0]
    assert binding.claim_id == "claim-1"
    assert binding.value == "publisher"
    assert not projection.violations()


def test_projection_persists_as_typed_graph_versum_layer(tmp_path):
    projection = LoomgroundAdapter().import_observation(OBSERVATION, claim_bindings=[{
        "claim_id": "claim-1", "subject_id": "agent", "axis_id": "party",
        "form_slot": "predicate.agent",
    }])
    root = save_projection(tmp_path / "loomground", projection)
    edges = load_edges(root / "relations.csv")
    assert not check_edge_contracts(edges)
    assert {edge["local_predicate"] for edge in edges} >= {"authority", "egress"}
    assert all(edge["system_id"] == "loomground-governance" for edge in edges)
    assert load_assignments(root / "assignments.csv")
    assert load_bindings(root / "bindings.csv")[0]["binding_id"].startswith("ndb:")


def test_export_preserves_supported_graph_shaped_subset():
    projection = LoomgroundAdapter().import_observation(OBSERVATION)
    exported = LoomgroundAdapter().export(projection)
    assert exported.media_type == "text/x-loomground"
    assert "actor agent party publisher grade L2" in exported.content
    assert "gate review risk high grade L1" in exported.content
    assert "cord agent -> review" in exported.content
    assert "cord review -> master" in exported.content


class _Runtime:
    def parse(self, source):
        return {"source": source}

    def validate(self, program):
        return {"valid": bool(program["source"])}

    def project(self, program):
        return OBSERVATION


def test_runtime_is_optional_and_implementation_neutral():
    adapter = LoomgroundAdapter(_Runtime())
    assert adapter.capabilities().parsing
    program = adapter.parse("actor agent")
    assert adapter.validate_program(program) == {"valid": True}
    assert adapter.project(program).identity.system_id == "loomground-governance"


def test_cli_projects_canonical_observation(tmp_path, capsys):
    source = tmp_path / "observation.json"
    source.write_text(json.dumps(OBSERVATION), encoding="utf-8")
    output = tmp_path / "graph"
    assert main(["adapt", "--adapter", "loomground", "--observation", str(source),
                 "--out", str(output)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["system"] == "loomground-governance"
    assert report["nodes"] >= 3
    assert (output / "relations.csv").exists()
    assert (output / "assignments.csv").exists()
