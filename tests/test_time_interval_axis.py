"""nd ``time`` axis: interval support, backward-compatible with the point-only past.

The core ``time`` axis has always been schema-declared ``value_type: "interval"``, but
until now the write path only ever stamped a bare point (``detected_year``). These tests
prove: a registry row carrying both ``detected_year`` and the new optional ``valid_to``
column now yields a real ``{from, to}`` interval (one coordinate, not a string set); a
row with only ``detected_year`` is byte-identical to pre-interval behaviour; two
intervals compare through the axis's overlaps/precedes/contains primitives; and a
malformed interval is rejected by ``AxisSpec.validate_value``.
"""
import json

from versum.io.consume import Registry, time_coordinate
from versum.identity.fingerprint import fingerprint, coord_values, _coord_value
from versum.store.index import index_folder
from versum.nd import Primitive, Truth, core_system
from versum.profiles.generic import PROFILE as GENERIC
import versum.profiles  # noqa: F401 — register built-in profiles

URN = "urn:kg:source:demo"


def _claims():
    return [{"item_id": "i1", "source_urn": URN, "predicate": "defines",
             "modality": "definitional", "quantification": "definite", "polarity": "D"}]


# ── consume.time_coordinate: the point/interval switch ───────────────
def test_time_coordinate_is_a_point_when_valid_to_absent():
    assert time_coordinate({"detected_year": "2016-04-27"}) == "2016-04-27"
    assert time_coordinate({"detected_year": "2016-04-27", "valid_to": ""}) == "2016-04-27"
    assert time_coordinate({}) == ""


def test_time_coordinate_is_an_interval_when_both_endpoints_present():
    assert time_coordinate({"detected_year": "2016-04-27", "valid_to": "2020-01-01"}) == \
        {"from": "2016-04-27", "to": "2020-01-01"}


# ── fingerprint: interval is ONE coordinate, never splatted to a string set ──
def test_fingerprint_time_is_a_set_for_a_bare_point_unchanged():
    fp = fingerprint(URN, _claims(), GENERIC, nd_context={"jurisdiction": "EU", "time": "2021"})
    assert fp["nd"]["time"] == {"2021"}
    assert isinstance(fp["nd"]["time"], set)


def test_fingerprint_time_is_one_interval_dict_not_a_string_set():
    interval = {"from": "2016-04-27", "to": "2020-01-01"}
    fp = fingerprint(URN, _claims(), GENERIC, nd_context={"jurisdiction": "EU", "time": interval})
    assert fp["nd"]["time"] == interval
    assert not isinstance(fp["nd"]["time"], set)


def test_coord_values_yields_one_interval_or_the_sorted_point_set():
    interval = {"from": "2016-04-27", "to": "2020-01-01"}
    assert coord_values({"time": interval}, "time") == [interval]
    assert coord_values({"time": "2021"}, "time") == ["2021"]
    assert coord_values({}, "time") == []
    # jurisdiction (never interval-shaped) is unaffected
    assert coord_values({"jurisdiction": "EU"}, "jurisdiction") == ["EU"]


def test_dict_missing_an_endpoint_is_not_treated_as_an_interval():
    # missing 'to' -> not a valid interval -> never returned as the single canonical dict
    value = _coord_value({"time": {"from": "2016-04-27"}}, "time")
    assert value != {"from": "2016-04-27"}
    assert coord_values({"time": {"from": "2016-04-27"}}, "time") != \
        [{"from": "2016-04-27"}]


# ── indexed source: from+to -> a real interval; point-only -> unchanged ──
def test_indexed_source_with_from_and_to_is_a_real_interval(tmp_path):
    rel = "doc.txt"
    (tmp_path / rel).write_text("A widget is defined as a thing.\n", encoding="utf-8")
    reg = Registry([{"original_path": rel, "filename": rel, "canonical_urn": "urn:x:source:iv",
                     "jurisdiction": "EU", "detected_year": "2016-04-27",
                     "valid_to": "2020-01-01"}])
    manifest = index_folder(tmp_path, "generic", consume=reg, library="lib", namespace="lib")
    fps = json.loads((tmp_path / ".versum" / "fingerprints.json").read_text())
    nd = fps["urn:x:source:iv"]["nd"]
    assert nd["time"] == {"from": "2016-04-27", "to": "2020-01-01"}

    rows = list(csv_rows(tmp_path / ".versum" / "nd" / "assignments.csv"))
    time_rows = [r for r in rows if r["axis_id"] == "time"]
    assert len(time_rows) == 1                                    # ONE coordinate, not two
    assert time_rows[0]["value"] == {"from": "2016-04-27", "to": "2020-01-01"}


def test_indexed_point_only_source_is_byte_identical_to_before(tmp_path):
    rel = "doc.txt"
    (tmp_path / rel).write_text("A widget is defined as a thing.\n", encoding="utf-8")
    reg = Registry([{"original_path": rel, "filename": rel, "canonical_urn": "urn:x:source:pt",
                     "jurisdiction": "EU", "detected_year": "2016-04-27"}])
    manifest = index_folder(tmp_path, "generic", consume=reg, library="lib", namespace="lib")
    fps = json.loads((tmp_path / ".versum" / "fingerprints.json").read_text())
    nd = fps["urn:x:source:pt"]["nd"]
    assert nd["time"] == ["2016-04-27"]                            # JSON round-trip of a set

    rows = list(csv_rows(tmp_path / ".versum" / "nd" / "assignments.csv"))
    time_rows = [r for r in rows if r["axis_id"] == "time"]
    assert len(time_rows) == 1
    assert time_rows[0]["value"] == "2016-04-27"                   # a bare string, as always
    assert time_rows[0]["method"] == "registry-attested"


def csv_rows(path):
    import csv
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            row["value"] = json.loads(row["value"])
            yield row


# ── AxisSpec.validate_value: a real interval branch ───────────────────
def test_axis_accepts_bare_point_and_valid_interval_shapes():
    axis = core_system().axes["time"]
    assert axis.validate_value("2016-04-27") == []                          # point, unchanged
    assert axis.validate_value({"from": "2016-04-27", "to": "2020-01-01"}) == []
    assert axis.validate_value(["2016-04-27", "2020-01-01"]) == []


def test_axis_rejects_malformed_interval():
    axis = core_system().axes["time"]
    assert axis.validate_value({"from": "2020-01-01", "to": "2016-04-27"})    # to before from
    assert axis.validate_value({"from": "", "to": "2020-01-01"})              # blank endpoint
    assert axis.validate_value(["2016-04-27"])                                # wrong arity
    assert axis.validate_value({"start": "2016-04-27", "end": "2020-01-01"})  # unknown keys
    assert axis.validate_value(42)                                            # not a date/pair


# ── two intervals compare through overlaps/precedes/contains ─────────
def test_two_intervals_compare_via_overlaps_precedes_contains():
    system = core_system()
    a = {"from": "2016-01-01", "to": "2019-12-31"}
    b = {"from": "2018-01-01", "to": "2021-06-30"}       # overlaps a
    c = {"from": "2020-01-01", "to": "2021-01-01"}       # disjoint from a, precedes nothing wrt b
    inner = {"from": "2017-01-01", "to": "2017-06-01"}   # contained by a

    assert system.relation("time", a, b, Primitive.OVERLAPS) == Truth.TRUE
    assert system.relation("time", a, c, Primitive.DISJOINT) == Truth.TRUE
    assert system.relation("time", a, c, Primitive.PRECEDES) == Truth.TRUE
    assert system.relation("time", c, a, Primitive.SUCCEEDS) == Truth.TRUE
    assert system.relation("time", a, inner, Primitive.CONTAINS) == Truth.TRUE
    assert system.relation("time", inner, a, Primitive.CONTAINED_BY) == Truth.TRUE
    assert system.relation("time", a, a, Primitive.EQUAL) == Truth.TRUE


def test_point_and_interval_are_comparable_as_a_degenerate_interval():
    system = core_system()
    point = "2017-03-01"
    span = {"from": "2016-01-01", "to": "2019-12-31"}
    assert system.relation("time", span, point, Primitive.CONTAINS) == Truth.TRUE
    assert system.relation("time", point, span, Primitive.CONTAINED_BY) == Truth.TRUE


def test_non_interval_axis_relation_is_unaffected():
    # jurisdiction stays ontology-table-driven; no geometric interpretation leaks in
    system = core_system()
    assert system.relation("jurisdiction", "EU", "DE", Primitive.CONTAINS) == Truth.UNKNOWN
