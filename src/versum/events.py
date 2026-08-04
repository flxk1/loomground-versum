"""Append-only mutation events and deterministic KG replay (seam K1).

The event log is the history. ``by-domain/``, ``_sync_state.json``, the nD manifest,
and the stamped graph version are projections that may be rebuilt from it. Projection
writers may replace their own files; previously appended events are never edited.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import fcntl
except ImportError:  # non-POSIX: no advisory locking; single-writer discipline applies
    fcntl = None

EVENT_LOG_FILE = "_events.jsonl"
EVENT_LOCK_FILE = "_events.lock"
EVENT_SCHEMA = "loomground.versum.event/v1"
ABSENT_DIGEST = "sha256:" + hashlib.sha256(b"null").hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def object_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _event_id(sequence: int, event_type: str, object_type: str, object_id: str,
              prior_digest: str, new_digest: str, observed_at: str) -> str:
    basis = [sequence, event_type, object_type, object_id, prior_digest, new_digest,
             observed_at]
    return "event:" + hashlib.sha256(_canonical_bytes(basis)).hexdigest()


def read_events(kg_root) -> tuple[dict, ...]:
    """Read and validate the complete ordered event stream."""
    path = Path(kg_root) / EVENT_LOG_FILE
    if not path.exists():
        return ()
    events = []
    latest: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            raise ValueError(f"blank event-log line {line_number}")
        event = json.loads(raw)
        sequence = len(events) + 1
        if event.get("schema") != EVENT_SCHEMA:
            raise ValueError(f"unknown event schema on line {line_number}")
        if event.get("sequence") != sequence:
            raise ValueError(f"non-contiguous event sequence on line {line_number}")
        event_type = str(event.get("event_type", ""))
        object_type = str(event.get("object_type", ""))
        observed_at = str(event.get("observed_at", ""))
        if not event_type or not object_type or not observed_at:
            raise ValueError(f"incomplete event envelope on line {line_number}")
        object_id = str(event.get("object_id", ""))
        if not object_id:
            raise ValueError(f"event on line {line_number} has no object_id")
        prior = str(event.get("prior_digest", ""))
        expected_prior = latest.get(object_id, ABSENT_DIGEST)
        if prior != expected_prior:
            raise ValueError(f"broken digest chain for {object_id!r} on line {line_number}")
        new = str(event.get("new_digest", ""))
        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise ValueError(f"invalid event payload on line {line_number}")
        expected_new = object_digest(payload)
        if new != expected_new:
            raise ValueError(f"invalid payload digest on line {line_number}")
        affected = sorted({str(value) for value in payload.get("affected_claim_ids", [])})
        if event.get("affected_claim_ids") != affected:
            raise ValueError(f"invalid affected_claim_ids on line {line_number}")
        expected_id = _event_id(sequence, event_type, object_type, object_id, prior, new,
                                observed_at)
        if event.get("event_id") != expected_id:
            raise ValueError(f"invalid event_id on line {line_number}")
        latest[object_id] = new
        events.append(event)
    return tuple(events)


@dataclass
class EventLog:
    """The store's single append-only writer handle.

    Constructing an ``EventLog`` takes an exclusive advisory lock on the store's
    journal (``_events.lock``) and holds it until :meth:`close` (or process
    exit). The journal is read only *after* the lock is held, so the in-memory
    sequence view can never go stale under a concurrent writer — two syncs
    against one store serialize instead of forking the event stream. Blocks
    until the lock is free; readers (:func:`read_events`) are unaffected.
    """

    root: Path

    def __init__(self, kg_root):
        self.root = Path(kg_root)
        self.path = self.root / EVENT_LOG_FILE
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock_fh = open(self.root / EVENT_LOCK_FILE, "a")
        if fcntl is not None:
            fcntl.flock(self._lock_fh, fcntl.LOCK_EX)
        self._events = list(read_events(self.root))
        self._latest = {event["object_id"]: event["new_digest"]
                        for event in self._events}

    def close(self) -> None:
        """Release the journal lock; the instance must not append afterwards."""
        if getattr(self, "_lock_fh", None) is not None:
            if fcntl is not None:
                fcntl.flock(self._lock_fh, fcntl.LOCK_UN)
            self._lock_fh.close()
            self._lock_fh = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:   # interpreter teardown may have dropped module globals
            pass

    def current_digest(self, object_id: str) -> str:
        return self._latest.get(object_id, ABSENT_DIGEST)

    def bootstrap_legacy_projection(self) -> dict | None:
        """Capture one replayable baseline when upgrading an eventless pre-K1 store.

        Dotfiles under ``by-domain/`` (Finder's ``.DS_Store`` etc.) are filesystem
        cruft, not store state, and are left out of the baseline.
        """
        if self._events:
            return None
        candidates = [self.root / "_sync_state.json", self.root / "_nd_systems.json"]
        by_domain = self.root / "by-domain"
        if by_domain.exists():
            candidates.extend(
                path for path in sorted(by_domain.rglob("*"))
                if path.is_file() and not any(part.startswith(".") for part in
                                              path.relative_to(by_domain).parts))
        files = {}
        for path in candidates:
            if not path.is_file():
                continue
            relpath = path.relative_to(self.root).as_posix()
            try:
                files[relpath] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"store file {relpath!r} is not UTF-8 text and cannot be captured "
                    "in the legacy baseline") from exc
        if not files:
            return None
        return self.append("projection.baseline", "projection", "projection:legacy", {
            "files": files,
            "affected_claim_ids": [],
        })

    def append(self, event_type: str, object_type: str, object_id: str,
               payload: dict, *, observed_at: str | None = None) -> dict:
        """Append one immutable event and return it."""
        if getattr(self, "_lock_fh", None) is None:
            raise ValueError("EventLog is closed — its journal lock has been released")
        if not event_type or not object_type or not object_id:
            raise ValueError("event_type, object_type, and object_id are required")
        sequence = len(self._events) + 1
        prior = self.current_digest(object_id)
        new = object_digest(payload)
        timestamp = observed_at or datetime.now(timezone.utc).isoformat()
        event = {
            "schema": EVENT_SCHEMA,
            "sequence": sequence,
            "event_id": _event_id(sequence, event_type, object_type, object_id, prior, new,
                                  timestamp),
            "event_type": event_type,
            "object_type": object_type,
            "object_id": object_id,
            "prior_digest": prior,
            "new_digest": new,
            "observed_at": timestamp,
            "affected_claim_ids": sorted({str(value) for value in
                                           payload.get("affected_claim_ids", [])}),
            "payload": payload,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")) + "\n")
        self._events.append(event)
        self._latest[object_id] = new
        return event


def source_object_id(library: str, relpath: str) -> str:
    return f"source:{library}:{relpath}"


def replay_events(events: Iterable[dict], target_root) -> dict:
    """Replay a validated stream into an empty target and return its graph version."""
    from .snapshot import mint_graph_version, stamp_graph_version
    from .sync import KGStore, SyncState

    target = Path(target_root)
    occupied = [target / EVENT_LOG_FILE, target / "by-domain", target / "_sync_state.json",
                target / "_nd_systems.json", target / "_graph_version.json"]
    if any(path.exists() for path in occupied):
        raise ValueError("replay target must not contain materialized store state")
    from .store import distribution, erasure

    store = KGStore(target)
    state = SyncState(target)
    count = 0
    saw_erasure = False
    saw_distribution = False
    for event in events:
        count += 1
        kind = event["event_type"]
        payload = event["payload"]
        if kind in distribution.DISTRIBUTION_EVENT_TYPES:
            # Publish/unpublish change no content — only which items flow DOWN to
            # descendants. The published set is refolded from the log below.
            saw_distribution = True
        elif kind in erasure.ERASURE_EVENT_TYPES:
            # Logical delete/restore change no content; purge strips content from the
            # replayed projection. The tombstone set is refolded from the log below.
            saw_erasure = True
            if kind == erasure.PURGE_EVENT:
                if payload.get("target_type") == "claim":
                    erasure._strip_claim_rows(target, item_id=payload["target_id"])
                else:
                    erasure._strip_concept(target, concept_id=payload["target_id"])
            elif kind == erasure.SOURCE_PURGE_EVENT:
                erasure._strip_source(target, payload["canonical_urn"])
        elif kind == "source.upserted":
            store.append_source(
                payload["domain"], payload["library"], payload["canonical_urn"],
                payload["provenance"], payload["relpath"], payload["sha1"],
                payload["claim_rows"], payload["fingerprint"])
            state.put(payload["library"], payload["relpath"], payload["state_entry"])
        elif kind == "source.removed":
            store.remove_source(payload["domain"], payload["canonical_urn"],
                                payload["relpath"])
            state.remove(payload["library"], payload["relpath"])
        elif kind == "source.seeded":
            state.put(payload["library"], payload["relpath"], payload["state_entry"])
        elif kind == "sync.profile.updated":
            state.profile = payload["profile"]
        elif kind == "nd.manifest.updated":
            (target / "_nd_systems.json").parent.mkdir(parents=True, exist_ok=True)
            (target / "_nd_systems.json").write_text(
                json.dumps(payload["manifest"], ensure_ascii=False, indent=2,
                           sort_keys=True) + "\n", encoding="utf-8")
        elif kind == "projection.baseline":
            for relpath, content in payload["files"].items():
                output = target / relpath
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(content, encoding="utf-8")
            state = SyncState(target)
        else:
            raise ValueError(f"unsupported event type {kind!r}")
    state.save()
    if saw_erasure:
        erasure.rebuild_erasure_projection(target)
    if saw_distribution:
        distribution.rebuild_distribution_projection(target)
    version = mint_graph_version(target)
    stamp_graph_version(target, version)
    return {"events": count, "graph_version": version, "target": str(target)}


def replay_event_log(source_root, target_root) -> dict:
    """Validate and replay ``source_root/_events.jsonl`` into an empty target.

    The history is copied byte-for-byte after its projections have rebuilt, making the
    target a self-contained replica rather than a projection detached from its source.
    """
    source = Path(source_root)
    target = Path(target_root)
    report = replay_events(read_events(source), target)
    log_path = source / EVENT_LOG_FILE
    if log_path.exists():
        (target / EVENT_LOG_FILE).write_bytes(log_path.read_bytes())
    return report


def changes_since(kg_root, watermark: int = 0) -> dict:
    """Return source changes after an inclusive history watermark (K5)."""
    events = read_events(kg_root)
    if watermark < 0 or watermark > len(events):
        raise ValueError(f"watermark must be between 0 and {len(events)}")
    changed: dict[str, set[str]] = {}
    for event in events[watermark:]:
        if event["event_type"] not in {"source.upserted", "source.removed"}:
            continue
        payload = event["payload"]
        canonical = str(payload.get("canonical_urn", ""))
        if canonical:
            changed.setdefault(canonical, set()).update(event["affected_claim_ids"])
    return {
        "from_watermark": watermark,
        "watermark": len(events),
        "changes": [
            {"canonical_urn": canonical, "affected_claim_ids": sorted(claim_ids)}
            for canonical, claim_ids in sorted(changed.items())
        ],
    }
