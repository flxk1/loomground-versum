from versum.store import graph
def test_typed_edges_are_valid_and_preserve_roles():
    rows = [
        graph.grounding_edge("g1", "claim:1", "concept:1", role="definition",
                             dimension="structural", evidence_ids=["span:1"]),
        graph.binding_edge("b1", "claim:1", "coord:1",
                           form_slot="quantification.range"),
        graph.scope_edge("s1", "coord:eu", "coord:de", primitive="contains",
                         evidence_ids=["ontology:1"]),
        graph.composition_edge("c1", "concept:1", "composition:1", role="condition"),
    ]
    assert graph.check_edge_contracts(rows) == []
    assert rows[0]["semantic_role"] == "definition"
    assert rows[1]["edge_family"] == "binding"
    assert rows[2]["semantic_role"] == "contains"


def test_edge_contract_rejects_family_type_and_dimension_mismatch():
    row = graph.binding_edge("b1", "claim:1", "coord:1", form_slot="predicate.agent")
    row["edge_type"] = "grounds"
    row["dimension"] = "imaginary"
    errors = graph.check_edge_contracts([row])
    assert any("invalid for binding" in e for e in errors)
    assert any("invalid Federation dimension" in e for e in errors)


def test_legacy_edge_remains_readable():
    legacy = {"edge_id": "old", "src_id": "a", "dst_id": "b",
              "edge_type": "rhymes_with"}
    assert graph.check_edge_contracts([legacy]) == []
