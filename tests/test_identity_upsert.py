# SPDX-License-Identifier: Apache-2.0
"""append_record identity-upsert — a MUTABLE entity supersedes in place.

The sink is an append-only, replayable transaction log; identity mode adds an
event-sourced latest-wins projection so a consumer with mutable records (an RVND
grounder work/claim edited in place) reads the current state, not every
superseded revision — while content-addressed records and facts are untouched.
"""
from __future__ import annotations

import pytest

from versum.capture import RuntimeCaptureError, append_record, append_records
from versum.store import erasure
from versum.store.erasure import tombstones_from_bytes
from versum.store.retrieve import (
    get_record, iter_records, iter_records_from_transactions, search_records,
)

_TXN_DIR = "_dimensioned_subgraph_transactions"


def _txn_bytes(root):
    """The sink's transaction payloads as in-memory bytes (what a sealed workspace
    holds in its decrypted store, never on plaintext disk)."""
    d = root / _TXN_DIR
    return [p.read_bytes() for p in sorted(d.glob("*.json"))] if d.exists() else []


def _store(tmp_path):
    root = tmp_path / ".versum"
    root.mkdir()
    return root


def _by_id(root, node_id):
    return [r for r in iter_records(root) if r["node_id"] == node_id]


def test_identity_upsert_supersedes_latest_wins(tmp_path):
    root = _store(tmp_path)
    append_record(root, record={"id": "w1", "title": "A"}, dimension="relational",
                  actor="grounder", identity=True, version="2026-08-06T10:00:00")
    append_record(root, record={"id": "w1", "title": "B"}, dimension="relational",
                  actor="grounder", identity=True, version="2026-08-06T11:00:00")
    rows = _by_id(root, "record:w1")
    assert len(rows) == 1, "identity id resolves to exactly one (latest) node"
    assert rows[0]["properties"]["record"]["title"] == "B"
    got = get_record(root, "record:w1")
    assert got is not None and got["properties"]["record"]["title"] == "B"


def test_identity_older_version_never_wins_regardless_of_write_order(tmp_path):
    root = _store(tmp_path)
    # write the NEWER version first, then an OLDER one — latest by version still wins
    append_record(root, record={"id": "w1", "title": "NEW"}, dimension="relational",
                  actor="g", identity=True, version="2026-08-06T12:00:00")
    append_record(root, record={"id": "w1", "title": "OLD"}, dimension="relational",
                  actor="g", identity=True, version="2026-08-06T09:00:00")
    got = get_record(root, "record:w1")
    assert got["properties"]["record"]["title"] == "NEW"


def test_identity_same_body_and_version_is_idempotent(tmp_path):
    root = _store(tmp_path)
    append_record(root, record={"id": "w1", "title": "A"}, dimension="relational",
                  actor="g", identity=True, version="v1")
    r = append_record(root, record={"id": "w1", "title": "A"}, dimension="relational",
                      actor="g", identity=True, version="v1")
    assert r["status"] == "unchanged"
    assert len(_by_id(root, "record:w1")) == 1


def test_content_addressed_default_keeps_every_version(tmp_path):
    root = _store(tmp_path)
    append_record(root, record={"id": "c1", "v": "x"}, dimension="relational", actor="g")
    append_record(root, record={"id": "c1", "v": "y"}, dimension="relational", actor="g")
    rows = [r for r in iter_records(root) if r["node_id"].startswith("record:c1")]
    assert len(rows) == 2, "content-addressed records coexist — backward-compatible"


def test_identity_erasure_hides_all_versions(tmp_path):
    root = _store(tmp_path)
    append_record(root, record={"id": "w1", "title": "A"}, dimension="relational",
                  actor="g", identity=True, version="v1")
    append_record(root, record={"id": "w1", "title": "B"}, dimension="relational",
                  actor="g", identity=True, version="v2")
    erasure.delete(root, "sink:record:w1", reason="forget", actor="g")
    assert _by_id(root, "record:w1") == []
    assert get_record(root, "record:w1") is None


def test_identity_requires_monotonic_version(tmp_path):
    root = _store(tmp_path)
    with pytest.raises(RuntimeCaptureError):
        append_record(root, record={"id": "w1"}, dimension="relational",
                      actor="g", identity=True)  # no version
    with pytest.raises(RuntimeCaptureError):
        append_record(root, record={"id": "w1"}, dimension="relational",
                      actor="g", identity=True, version="   ")  # blank version


def test_append_records_batch_writes_one_transaction(tmp_path):
    root = _store(tmp_path)
    txn_dir = root / "_dimensioned_subgraph_transactions"
    append_records(root, dimension="relational", actor="g", records=[
        {"record": {"id": "w1", "title": "A"}, "version": "v1"},
        {"record": {"id": "w2", "title": "B"}, "version": "v1"},
        {"record": {"id": "w3", "title": "C"}, "version": "v1"},
    ])
    # three records, ONE transaction file (one durable write)
    assert txn_dir.exists() and len(list(txn_dir.glob("*.json"))) == 1
    ids = {r["node_id"] for r in iter_records(root)}
    assert {"record:w1", "record:w2", "record:w3"} <= ids


def test_append_records_supersede_and_idempotent(tmp_path):
    root = _store(tmp_path)
    append_records(root, dimension="relational", actor="g", records=[
        {"record": {"id": "w1", "title": "A"}, "version": "v1"}])
    # a bumped version in a later batch supersedes on read
    append_records(root, dimension="relational", actor="g", records=[
        {"record": {"id": "w1", "title": "B"}, "version": "v2"}])
    assert get_record(root, "record:w1")["properties"]["record"]["title"] == "B"
    # re-appending the identical batch is idempotent
    r = append_records(root, dimension="relational", actor="g", records=[
        {"record": {"id": "w1", "title": "B"}, "version": "v2"}])
    assert r["status"] == "unchanged"


def test_append_records_empty_is_noop(tmp_path):
    root = _store(tmp_path)
    assert append_records(root, dimension="relational", actor="g", records=[]) is None
    assert list(iter_records(root)) == []


def test_append_records_requires_version_per_item(tmp_path):
    root = _store(tmp_path)
    with pytest.raises(RuntimeCaptureError):
        append_records(root, dimension="relational", actor="g",
                       records=[{"record": {"id": "w1"}}])  # no version


def test_from_transactions_matches_on_disk_reader(tmp_path):
    root = _store(tmp_path)
    append_record(root, record={"id": "w1", "title": "A"}, dimension="relational",
                  actor="g", identity=True, version="v1")
    append_record(root, record={"id": "w1", "title": "B"}, dimension="relational",
                  actor="g", identity=True, version="v2")   # supersedes
    append_record(root, record={"id": "c1", "v": "x"}, dimension="relational", actor="g")

    on_disk = sorted((r["node_id"], r["properties"]["record"])
                     for r in iter_records(root))
    in_mem = sorted((r["node_id"], r["properties"]["record"])
                    for r in iter_records_from_transactions(_txn_bytes(root)))
    assert in_mem == on_disk
    # latest-wins holds through the in-memory reader too
    w1 = [r for r in iter_records_from_transactions(_txn_bytes(root))
          if r["node_id"] == "record:w1"]
    assert len(w1) == 1 and w1[0]["properties"]["record"]["title"] == "B"


def test_from_transactions_honors_tombstone_bytes(tmp_path):
    root = _store(tmp_path)
    append_record(root, record={"id": "w1", "title": "A"}, dimension="relational",
                  actor="g", identity=True, version="v1")
    append_record(root, record={"id": "w2", "title": "B"}, dimension="relational",
                  actor="g", identity=True, version="v1")
    erasure.delete(root, "sink:record:w1", reason="t", actor="g")

    txns = _txn_bytes(root)
    erasure_bytes = (root / "_erasure.json").read_bytes()
    tombs = tombstones_from_bytes(erasure_bytes)
    ids = {r["node_id"] for r in iter_records_from_transactions(txns, tombstones=tombs)}
    assert "record:w2" in ids and "record:w1" not in ids
    # no tombstones → the erased node is NOT filtered (caller opted out)
    ids_all = {r["node_id"] for r in iter_records_from_transactions(txns)}
    assert {"record:w1", "record:w2"} <= ids_all


def test_from_transactions_empty_and_garbage_safe(tmp_path):
    assert list(iter_records_from_transactions([])) == []
    assert list(iter_records_from_transactions([b"not json", "{}", 123])) == []
    assert tombstones_from_bytes(None).hidden_nodes == frozenset()


def test_identity_record_is_searchable_and_returns_latest(tmp_path):
    root = _store(tmp_path)
    append_record(root, record={"id": "w1", "problem": {"summary": "alpha topic"}},
                  dimension="relational", actor="g", identity=True, version="v1")
    append_record(root, record={"id": "w1", "problem": {"summary": "beta topic revised"}},
                  dimension="relational", actor="g", identity=True, version="v2")
    hits = search_records(root, "beta topic revised", k=5)
    w1 = [h for h in hits if (h.get("node_id") or h.get("id")) == "record:w1"]
    assert w1, "identity record is findable"
    assert w1[0]["properties"]["record"]["problem"]["summary"] == "beta topic revised"
