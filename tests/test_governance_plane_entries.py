"""Governance plane on versum entries: produce, entry -> observation bindings, round-trip.

A sentence entry (``item_id``) that the governance plane claims is bound, through
``LoomgroundAdapter``, to the coordinates of a governance observation; every published
projectable conformance vector and every worked example reads back field for field
(rule 4).
"""
from __future__ import annotations

import pytest

governance = pytest.importorskip("loomground_governance")
pytest.importorskip("loomground_governance.plane")

from versum.integrations.loomground import LoomgroundAdapter  # noqa: E402
from versum.planes import DescriptorPlane, build_source_entries, sentence_spans  # noqa: E402

S3 = "The controller must not make a solely automated decision on a credit application."
CASE = (
    "The bank is a controller. The scoring model is part of the credit system. "
    f"{S3} The controller may use the score to prepare a decision. "
    "The controller knows that the training data is inaccurate. "
    "A reviewer shall examine every rejection before it is sent. "
    "The review follows the automated scoring."
)
SOURCE = "urn:test:credit-decision"


@pytest.fixture(scope="module")
def plane():
    return DescriptorPlane.from_descriptor(governance.plane_descriptor(),
                                           entry_name="governance")


@pytest.fixture(scope="module")
def draft_decide():
    vector = next(v for v in governance.iter_vectors() if v.name == "draft-decide")
    return vector.json("expected.json")


@pytest.fixture(scope="module")
def indexed(plane):
    return build_source_entries(CASE, SOURCE, [plane])


def _s3_entry(indexed):
    [entry] = [e for e in indexed.entries if e["text"] == S3]
    return entry


def test_produce_s3_binds_the_reserved_decide_gate(plane):
    [claim] = plane.produce(S3)
    assert claim["gate"] == "decide"
    assert claim["relation"] == "reservation"
    assert claim["coordinates"]["verdict"] == "reserved"
    assert claim["coordinates"]["node_class"] == "gate"


def test_produce_is_empty_for_every_other_case_sentence(plane):
    for start, end in sentence_spans(CASE):
        sentence = CASE[start:end]
        if sentence != S3:
            assert plane.produce(sentence) == [], sentence


def test_index_assigns_governance_coordinates_to_the_s3_entry(indexed):
    entry = _s3_entry(indexed)
    assert entry["entry_kind"] == "sentence"
    assert CASE[entry["span_start"]:entry["span_end"]] == S3
    assert entry["planes"] == "governance"
    assert entry["dominant_dimension"] == "intentional"      # reservation -> intentional
    rows = {(a.axis_id, a.value) for a in indexed.assignments
            if a.subject_id == entry["item_id"]}
    assert rows == {("node_class", "gate"), ("token_kind", "automated_decision"),
                    ("verdict", "reserved")}
    assert all(a.system_version == governance.language_version()
               for a in indexed.assignments)
    others = [e for e in indexed.entries if e["text"] != S3]
    assert len(others) == 6 and all(e["planes"] == "" for e in others)


def test_entry_item_id_binds_to_the_governance_observation(indexed, draft_decide):
    adapter = LoomgroundAdapter()
    entry = _s3_entry(indexed)
    projection = adapter.project_entries(draft_decide, indexed.claims)
    assert not projection.violations()
    bound = {(b.claim_id, b.form_slot, b.axis_id, b.value) for b in projection.bindings}
    assert bound == {
        (entry["item_id"], "predicate.agent", "node_class", "gate"),
        (entry["item_id"], "predicate.patient", "token_kind", "automated_decision"),
    }
    by_assignment = {a.assignment_id: a for a in projection.assignments}
    subjects = {by_assignment[b.assignment_id].subject_id for b in projection.bindings}
    assert "decide" in subjects                        # the gate, not the draft gate
    assert "draft" not in subjects
    assert all(b.semantic_role == "reservation" for b in projection.bindings)


def test_entry_binding_fails_closed(indexed, draft_decide):
    adapter = LoomgroundAdapter()
    without_gate = {**draft_decide,
                    "nodes": [n for n in draft_decide["nodes"] if n["id"] != "decide"],
                    "cords": [c for c in draft_decide["cords"] if "decide" not in c.values()]}
    with pytest.raises(ValueError, match="gate 'decide' is not declared"):
        adapter.project_entries(without_gate, indexed.claims)
    unreserved = {**draft_decide, "reservations": []}
    with pytest.raises(ValueError, match="no coordinate in the observation"):
        adapter.project_entries(unreserved, indexed.claims)
    stale = [{**row, "language_version": "0.0.0"} for row in indexed.claims]
    with pytest.raises(ValueError, match="stale"):
        adapter.project_entries(draft_decide, stale)


def test_claims_of_other_planes_are_not_bound(indexed, draft_decide):
    foreign = [{**row, "plane": "deontic"} for row in indexed.claims]
    assert LoomgroundAdapter().project_entries(draft_decide, foreign).bindings == []


def test_published_examples_round_trip_through_entries(plane):
    examples = plane.examples()
    assert examples
    for example in examples:
        out = build_source_entries(example["sentence"], SOURCE, [plane])
        assert [row["claim"] for row in out.claims] == example["expected"]
        assert all(row["language_version"] == plane.language_version for row in out.claims)


def test_projectable_conformance_vectors_round_trip():
    adapter = LoomgroundAdapter()
    published = governance.plane_descriptor()["observations"]
    patch = [v for v in governance.iter_vectors() if v.kind == "patch"]
    assert 0 < len(published) <= len(patch)
    for item in published:
        projection = adapter.import_observation(item["observation"])
        assert not projection.violations(), item["name"]
        assert adapter.read_observation(projection) == item["observation"], item["name"]
