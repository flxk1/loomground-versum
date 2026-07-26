import pytest

from versum.composition import Composition, Participant, load_compositions
from versum.store.graph import Claim, save_claims
from versum.nd import AxisSpec, Binding, BindingRule, CoordinateAssignment, NDSystem
from versum.concept.semantics import persist_claim_semantics


def _claim_store(tmp_path):
    root = tmp_path / ".versum"
    root.mkdir()
    save_claims(root / "claims.csv", [Claim("claim:1", "urn:test:source", text="Rule")],
                "generic")
    return root


def _records():
    system = NDSystem(
        "rule-nd", "rule.nd", "1", "1",
        {"modal": AxisSpec("modal", "string", vocabulary_mode="open")},
        bindings=(BindingRule("modality.bearer", ("modal",)),))
    composition = Composition(
        "cmp:1", "deontic",
        (Participant("bearer", "actor:controller", ("claim:1",)),
         Participant("action", "action:erase", ("claim:1",))))
    assignment = CoordinateAssignment(
        "claim:1", system.system_id, system.version, "modal", "obligation",
        "urn:test:source", "rule-nd", assignment_id="nda:1")
    binding = Binding(
        "claim:1", "modality.bearer", "modal", "nda:1", "modal", "obligation",
        "urn:test:source", "rule-nd", binding_id="ndb:1")
    return system, composition, assignment, binding


def test_persist_claim_semantics_is_native_and_idempotent(tmp_path):
    root = _claim_store(tmp_path)
    system, composition, assignment, binding = _records()
    first = persist_claim_semantics(root, compositions=[composition], systems=[system],
                                    assignments=[assignment], bindings=[binding])
    second = persist_claim_semantics(root, compositions=[composition], systems=[system],
                                     assignments=[assignment], bindings=[binding])

    assert first == second == {"compositions": 1, "assignments": 1,
                               "bindings": 1, "systems": 1}
    assert load_compositions(root / "compositions.jsonl") == [composition]


def test_persist_claim_semantics_rejects_unknown_evidence_without_writes(tmp_path):
    root = _claim_store(tmp_path)
    bad = Composition(
        "cmp:bad", "deontic",
        (Participant("bearer", "actor:x", ("claim:missing",)),
         Participant("action", "action:y", ("claim:missing",))))
    with pytest.raises(ValueError, match="unknown claims"):
        persist_claim_semantics(root, compositions=[bad])
    assert not (root / "compositions.jsonl").exists()
