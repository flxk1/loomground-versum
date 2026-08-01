"""K1 falsifiers: immutable mutation history and byte-identical replay."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from versum import sync
from versum.events import (EVENT_LOG_FILE, EVENT_SCHEMA, changes_since, read_events,
                           replay_event_log)

DOC_A = "A widget is defined as a small thing. A widget causes value.\n"
DOC_B = "A gadget is defined as a device. A gadget enables motion.\n"
DOC_C = "A sprocket is defined as a wheel. A sprocket prevents drift.\n"


def _config(tmp_path: Path) -> dict:
    root = tmp_path / "source"
    library = tmp_path / "library"
    library.mkdir()
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "kg_root": str(root), "profile_id": "generic",
        "libraries": [{"id": "lib", "root_path": str(library),
                       "urn_namespace": "test", "registry_csv": None}],
    }), encoding="utf-8")
    return sync.load_config(path)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _projection_bytes(root: Path) -> dict[str, bytes]:
    included = {EVENT_LOG_FILE, "_sync_state.json", "_nd_systems.json", "_graph_version.json"}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and (path.name in included or "by-domain" in path.parts)
    }


def test_event_log_is_append_only_and_no_change_is_a_noop(tmp_path):
    cfg = _config(tmp_path)
    doc = Path(cfg["libraries"][0]["root_path"]) / "alpha" / "a.txt"
    _write(doc, DOC_A)

    sync.sync_once(cfg)
    log_path = Path(cfg["kg_root"]) / EVENT_LOG_FILE
    first_bytes = log_path.read_bytes()
    events = read_events(cfg["kg_root"])
    assert len(events) == 2
    assert events[0]["event_type"] == "sync.profile.updated"
    assert events[0]["sequence"] == 1
    assert events[0]["object_id"] == "sync:profile"
    assert events[0]["payload"]["profile"]["id"] == "generic"
    event = events[1]
    assert event["schema"] == EVENT_SCHEMA
    assert event["sequence"] == 2
    assert event["event_type"] == "source.upserted"
    assert event["object_id"] == "source:lib:alpha/a.txt"
    assert event["prior_digest"].startswith("sha256:")
    assert event["new_digest"].startswith("sha256:")
    assert event["observed_at"]
    assert event["affected_claim_ids"]

    sync.sync_once(cfg)
    assert log_path.read_bytes() == first_bytes

    stat = doc.stat()
    _write(doc, DOC_A + DOC_C)
    os.utime(doc, (stat.st_mtime + 10, stat.st_mtime + 10))
    sync.sync_once(cfg)
    assert log_path.read_bytes().startswith(first_bytes)
    assert [event["event_type"] for event in read_events(cfg["kg_root"])] == [
        "sync.profile.updated", "source.upserted", "source.removed",
        "source.upserted"]


def test_replay_from_empty_reproduces_materialized_store_byte_identically(tmp_path):
    cfg = _config(tmp_path)
    library = Path(cfg["libraries"][0]["root_path"])
    a = library / "alpha" / "a.txt"
    b = library / "beta" / "b.txt"
    _write(a, DOC_A)
    _write(b, DOC_B)
    sync.sync_once(cfg)

    stat = a.stat()
    _write(a, DOC_A + DOC_C)
    os.utime(a, (stat.st_mtime + 10, stat.st_mtime + 10))
    b.unlink()
    report = sync.sync_once(cfg)
    assert report["changed"] == 1 and report["removed"] == 1

    source = Path(cfg["kg_root"])
    target = tmp_path / "replayed"
    replay = replay_event_log(source, target)
    assert replay["events"] == len(read_events(source))
    assert replay["graph_version"] == report["graph_version"]
    assert _projection_bytes(target) == _projection_bytes(source)


def test_seed_state_is_replayable_history(tmp_path):
    cfg = _config(tmp_path)
    library = Path(cfg["libraries"][0]["root_path"])
    _write(library / "alpha" / "a.txt", DOC_A)
    sync.seed_state(cfg)
    first_log = (Path(cfg["kg_root"]) / EVENT_LOG_FILE).read_bytes()
    sync.seed_state(cfg)
    assert (Path(cfg["kg_root"]) / EVENT_LOG_FILE).read_bytes() == first_log
    sync.sync_once(cfg)

    source = Path(cfg["kg_root"])
    target = tmp_path / "seed-replayed"
    replay_event_log(source, target)
    assert _projection_bytes(target) == _projection_bytes(source)
    assert read_events(source)[0]["event_type"] == "source.seeded"


def test_tampered_event_payload_fails_closed(tmp_path):
    cfg = _config(tmp_path)
    library = Path(cfg["libraries"][0]["root_path"])
    _write(library / "alpha" / "a.txt", DOC_A)
    sync.sync_once(cfg)

    source = Path(cfg["kg_root"])
    tampered = tmp_path / "tampered"
    tampered.mkdir()
    event = json.loads((source / EVENT_LOG_FILE).read_text().splitlines()[0])
    event["payload"]["canonical_urn"] = "urn:tampered"
    (tampered / EVENT_LOG_FILE).write_text(json.dumps(event) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="payload digest"):
        read_events(tampered)


def test_replay_refuses_nonempty_projection_target(tmp_path):
    cfg = _config(tmp_path)
    library = Path(cfg["libraries"][0]["root_path"])
    _write(library / "alpha" / "a.txt", DOC_A)
    sync.sync_once(cfg)
    target = tmp_path / "occupied"
    (target / "by-domain").mkdir(parents=True)
    with pytest.raises(ValueError, match="must not contain"):
        replay_event_log(cfg["kg_root"], target)


def test_pre_k1_store_gets_a_replayable_legacy_baseline(tmp_path):
    cfg = _config(tmp_path)
    library = Path(cfg["libraries"][0]["root_path"])
    _write(library / "alpha" / "a.txt", DOC_A)
    sync.sync_once(cfg)
    source = Path(cfg["kg_root"])
    (source / EVENT_LOG_FILE).unlink()
    before = _projection_bytes(source)

    sync.sync_once(cfg)

    assert read_events(source)[0]["event_type"] == "projection.baseline"
    target = tmp_path / "legacy-replayed"
    replay_event_log(source, target)
    assert {key: value for key, value in _projection_bytes(target).items()
            if key != EVENT_LOG_FILE} == before


def test_legacy_baseline_skips_finder_cruft_in_by_domain(tmp_path):
    cfg = _config(tmp_path)
    library = Path(cfg["libraries"][0]["root_path"])
    _write(library / "alpha" / "a.txt", DOC_A)
    sync.sync_once(cfg)
    source = Path(cfg["kg_root"])
    (source / EVENT_LOG_FILE).unlink()
    (source / "by-domain" / ".DS_Store").write_bytes(b"\x00\x01Bud1\x80\xff")
    (source / "by-domain" / "alpha" / ".DS_Store").write_bytes(b"\x00\x01Bud1\x80\xff")

    sync.sync_once(cfg)

    baseline = read_events(source)[0]
    assert baseline["event_type"] == "projection.baseline"
    assert not any(".DS_Store" in relpath for relpath in baseline["payload"]["files"])


def test_legacy_baseline_names_a_non_utf8_store_file(tmp_path):
    cfg = _config(tmp_path)
    library = Path(cfg["libraries"][0]["root_path"])
    _write(library / "alpha" / "a.txt", DOC_A)
    sync.sync_once(cfg)
    source = Path(cfg["kg_root"])
    (source / EVENT_LOG_FILE).unlink()
    (source / "by-domain" / "alpha" / "rogue.bin").write_bytes(b"\x80\x81\xfe\xff")

    with pytest.raises(ValueError, match="by-domain/alpha/rogue.bin"):
        sync.sync_once(cfg)


def test_change_feed_names_only_changed_source_and_exact_claims(tmp_path):
    cfg = _config(tmp_path)
    library = Path(cfg["libraries"][0]["root_path"])
    a = library / "a.txt"
    b = library / "b.txt"
    _write(a, DOC_A)
    _write(b, DOC_B)
    sync.sync_once(cfg)
    watermark = len(read_events(cfg["kg_root"]))
    unchanged_canonical = sync.SyncState(cfg["kg_root"]).get("lib", "b.txt")["canonical_urn"]

    stat = a.stat()
    _write(a, DOC_A + DOC_C)
    os.utime(a, (stat.st_mtime + 10, stat.st_mtime + 10))
    sync.sync_once(cfg)
    feed = changes_since(cfg["kg_root"], watermark)

    assert feed["changes"]
    assert unchanged_canonical not in {change["canonical_urn"] for change in feed["changes"]}
    expected = {event_claim for event in read_events(cfg["kg_root"])[watermark:]
                for event_claim in event["affected_claim_ids"]}
    actual = {claim_id for change in feed["changes"]
              for claim_id in change["affected_claim_ids"]}
    assert actual == expected
    assert changes_since(cfg["kg_root"], feed["watermark"])["changes"] == []


def test_change_feed_rejects_invalid_watermark(tmp_path):
    with pytest.raises(ValueError, match="watermark"):
        changes_since(tmp_path, 1)
