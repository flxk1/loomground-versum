"""Rule 4 for the deontic plane: every published example and conformance vector,
projected into the versum by ``produce()`` and read back from the index, reproduces
the plane's own output field for field; and the credit-decision case lands on the
right entries with D1 dimensions."""
from __future__ import annotations

import csv
import json

import pytest

from versum import planes as pl
from versum import position5d as p5
from versum.deontic import deontic_plane
from versum.nd import load_assignments, load_bindings
from versum.store.index import index_folder

import deontic  # noqa: E402 — a hard dependency; never skipped

CREDIT = (
    "The bank is a controller. "
    "The scoring model is part of the credit system. "
    "The controller must not make a solely automated decision on a credit application. "
    "The controller may use the score to prepare a decision. "
    "The controller knows that the training data is inaccurate. "
    "A reviewer shall examine every rejection before it is sent. "
    "The review follows the automated scoring."
)


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_published_examples_round_trip_through_the_index(tmp_path):
    plane = deontic_plane()
    examples = plane.examples()
    assert examples
    for i, ex in enumerate(examples):
        (tmp_path / f"ex{i:02d}.txt").write_text(ex["sentence"] + "\n", encoding="utf-8")
    index_folder(tmp_path, "generic", planes=[deontic_plane()])
    v = tmp_path / ".versum"
    sources = {r["path"]: r["source_urn"] for r in _rows(v / "sources.csv")}
    claims = [json.loads(x) for x in (v / "entry_claims.jsonl").read_text().splitlines()]
    for i, ex in enumerate(examples):
        got = [c for c in claims if c["source_urn"] == sources[f"ex{i:02d}.txt"]]
        assert [c["claim"] for c in got] == ex["expected"], ex["name"]
        assert all(c["language_version"] == deontic.language_version() for c in got)


def test_conformance_vectors_read_back_as_the_language_output(tmp_path):
    plane = deontic_plane()
    for vec in deontic.conformance_manifest()["vectors"]:
        if vec["kind"] != "statement":
            continue
        base = deontic.artifact_path("conformance", "vectors", vec["name"])
        sentence = base.joinpath("input.deo").read_text(encoding="utf-8").strip()
        expected = json.loads(base.joinpath("expected.json").read_text(encoding="utf-8"))
        built = pl.build_source_entries(sentence, f"urn:t:{vec['name']}", [plane])
        (claim,) = built.claims
        assert claim["claim"]["statement"] == expected
        coords = {a.axis_id: a.value for a in built.assignments}
        for field, value in expected.items():
            if field == "negated" or value:
                assert coords[field] == value


def test_credit_case_entries_carry_deontic_coordinates_and_d1_dimensions(tmp_path):
    (tmp_path / "credit.txt").write_text(CREDIT + "\n", encoding="utf-8")
    index_folder(tmp_path, "generic", planes=[deontic_plane()])
    v = tmp_path / ".versum"
    entries = _rows(v / "entries.csv")
    assert len(entries) == 7
    by_idx = {int(e["sentence_index"]): e for e in entries}
    rows = [r for r in load_assignments(v / "nd" / "assignments.csv")
            if r["system_id"] == "loomground-deontic"]
    coords: dict = {}
    for r in rows:
        assert r["system_version"] == deontic.language_version()
        coords.setdefault(r["subject_id"], {})[r["axis_id"]] = r["value"]

    # Round 4: an operator (O/P/F) is an ought, not a fact on the 5D manifold — the
    # deontic plane's binding is always {}. With ONLY the deontic plane installed (no
    # factual plane to lower the norm's content, no governance plane on s3), nothing
    # contributes to any of these entries' 5D position: they land on the default/no-plane
    # basis, dominant "relational" (versum.position5d.NO_PLANE_DOMINANT).
    expected = {2: ("F", "controller", "relational"),
                3: ("P", "controller", "relational"),
                5: ("O", "reviewer", "relational")}
    for idx, e in by_idx.items():
        if idx in expected:
            op, bearer, dim = expected[idx]
            c = coords[e["item_id"]]
            assert (c["operator"], c["bearer"]) == (op, bearer)
            assert e["dominant_dimension"] == dim
            assert e["position_basis"] == p5.BASIS_DEFAULT
            assert e["planes"] == "deontic"
        else:
            assert e["item_id"] not in coords and e["planes"] == ""
    assert coords[by_idx[5]["item_id"]]["condition"] == "before it is sent"
    bindings = load_bindings(v / "nd" / "bindings.csv")
    assert {b["form_slot"] for b in bindings} >= {
        "statement.operator", "statement.bearer", "statement.action"}


def test_out_of_vocabulary_operator_fails_closed():
    plane = deontic_plane()

    def bad_produce(sentence, context=None):
        claims = plane.produce(sentence)
        claims[0]["coordinates"]["operator"] = "Q"
        return claims

    raw = {"plane": "deontic", "language_version": plane.language_version,
           "nd_system": json.loads(deontic.artifact_path("nd-system.json").read_text()),
           "binding": dict(plane.binding()), "produce": bad_produce}
    with pytest.raises(pl.PlaneIndexError, match="operator"):
        pl.build_source_entries("O(controller : act)", "urn:t:bad", pl.load_planes([raw]))
