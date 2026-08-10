# SPDX-License-Identifier: Apache-2.0
"""append_record — a full runtime pair as first-class knowledge, losslessly."""
from __future__ import annotations

import versum
from versum.capture import append_record


_PAIR = {
    "id": "sha256:deadbeef",
    "problem": {
        "id": "p1",
        "scope": "gdpr",
        "summary": "Does Article 17 grant a right to erasure to the data subject?",
        "facets": {
            "deontic": {"operator": "O", "bearer": "controller", "action": "erase"},
            "gdpr": {"article": "17", "tags": ["erasure", "data-subject-rights"]},
            "nested": {"a": {"b": ["deep", "facet", "value"]}},
        },
    },
    "solution": {
        "id": "s1",
        "body": "Yes — the controller must erase without undue delay, subject to exceptions.",
        "confidence": 0.9,
    },
}


def _store(tmp_path):
    root = tmp_path / ".versum"
    root.mkdir()
    return root


def test_append_record_roundtrips_losslessly(tmp_path):
    root = _store(tmp_path)
    receipt = append_record(root, record=_PAIR, dimension="relational", actor="tester")
    assert receipt["status"] == "inserted"

    # findable through the runtime record search over the sink
    hits = versum.search_records(root, "right to erasure data subject", k=5)
    assert hits, "record must be searchable by its derived statement"
    node_id = hits[0].get("node_id") or hits[0].get("id")
    assert node_id

    rec = versum.get_record(root, node_id)
    assert rec is not None
    # the FULL pair body is preserved verbatim in properties.record — no facet loss
    props = rec.get("properties", rec)
    stored = props.get("record")
    assert stored == _PAIR, "the whole pair (incl. nested facets) must round-trip"
    assert props.get("grounding") == "runtime"


def test_append_record_is_idempotent(tmp_path):
    root = _store(tmp_path)
    r1 = append_record(root, record=_PAIR, dimension="relational", actor="tester")
    r2 = append_record(root, record=_PAIR, dimension="relational", actor="tester")
    assert r1["status"] == "inserted"
    assert r2["status"] == "unchanged"


def test_append_record_no_edges_is_valid(tmp_path):
    root = _store(tmp_path)
    minimal = {"id": "x:1", "problem": {"summary": "q"}, "solution": {"body": "a"}}
    receipt = append_record(root, record=minimal, dimension="relational", actor="a")
    assert receipt["status"] == "inserted"


def test_iter_records_enumerates_all(tmp_path):
    root = _store(tmp_path)
    append_record(root, record=_PAIR, dimension="relational", actor="t")
    append_record(root, record={"id": "x:2", "problem": {"summary": "other q"},
                                "solution": {"body": "b"}},
                  dimension="relational", actor="t")
    recs = list(versum.iter_records(root))
    ids = {r["properties"]["record"]["id"] for r in recs
           if isinstance(r.get("properties", {}).get("record"), dict)}
    assert {"sha256:deadbeef", "x:2"} <= ids
