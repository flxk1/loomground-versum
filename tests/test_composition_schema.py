import pytest

from versum.composition import (
    Composition, CompositionKind, Participant, load_compositions, save_compositions,
)
from versum.store.graph import check_edge_contracts


@pytest.mark.parametrize("kind,participants", [
    ("entity", [Participant("evidence", "claim:1", ("span:1",))]),
    ("deontic", [Participant("bearer", "actor:1", ("claim:1",)),
                 Participant("action", "action:1", ("claim:1",))]),
    ("process", [Participant("step:1", "concept:1", ("claim:1",)),
                 Participant("step:2", "concept:2", ("claim:2",))]),
    ("conditional", [Participant("antecedent", "condition:1", ("claim:1",)),
                     Participant("consequent", "concept:1", ("claim:2",))]),
    ("relation", [Participant("subject", "concept:1", ("claim:1",)),
                  Participant("operator", "predicate:1", ("claim:1",)),
                  Participant("object", "concept:2", ("claim:1",))]),
    ("temporal_diff", [Participant("before", "concept:v1", ("claim:1",)),
                      Participant("after", "concept:v2", ("claim:2",))]),
    ("composite", [Participant("member:1", "concept:1", ("claim:1",)),
                   Participant("member:2", "concept:2", ("claim:2",))]),
])
def test_supported_composition_shapes(kind, participants):
    c = Composition("cmp:1", kind, tuple(participants), method_version="manual-v1")
    assert c.violations() == []
    assert check_edge_contracts(c.edge_rows()) == []


def test_composition_requires_roles_and_grounding():
    c = Composition("cmp:1", CompositionKind.CONDITIONAL.value,
                    (Participant("antecedent", "condition:1"),))
    errors = c.violations()
    assert any("consequent" in e for e in errors)
    assert any("grounding evidence" in e for e in errors)


def test_composition_store_round_trips_nested_participants_and_scope(tmp_path):
    composition = Composition(
        "cmp:rule:1", "deontic",
        (Participant("bearer", "actor:controller", ("claim:1",)),
         Participant("action", "action:erase", ("claim:1",))),
        label="controller must erase", method_version="rule-nd@1",
        nd_scope={"modal": "prohibition", "jurisdiction": ["eu"]},
    )
    path = tmp_path / ".versum" / "compositions.jsonl"
    save_compositions(path, [composition])

    assert load_compositions(path) == [composition]


def test_composition_store_rejects_invalid_shape(tmp_path):
    invalid = Composition(
        "cmp:rule:1", "deontic",
        (Participant("bearer", "actor:controller", ("claim:1",)),),
    )
    with pytest.raises(ValueError, match="requires role 'action'"):
        save_compositions(tmp_path / "compositions.jsonl", [invalid])
