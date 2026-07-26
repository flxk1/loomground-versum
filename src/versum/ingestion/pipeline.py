"""Resumable, recorded orchestration of the deterministic inbox passes."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import acquire
from . import provenance
from . import route
from . import year


PIPELINE_VERSION = 1
RUNS_DIR = "_runs"


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _run_id(inbox: Path, review: Path, profile_id: str) -> str:
    state = {"pipeline_version": PIPELINE_VERSION, "profile": profile_id,
             "review": str(review.resolve()), "ledger": acquire.load_log(inbox)}
    return hashlib.sha256(_canonical(state)).hexdigest()[:16]


def process(inbox_dir, review_dir, profile_id="generic", *, id_year=None) -> dict:
    """Run provenance → year → review routing and persist an auditable run record.

    Every stage is idempotent. A completed record for the exact same input state is returned
    without repeating work; interrupted states simply run again through the safe stage seams.
    """
    inbox = Path(inbox_dir).resolve()
    review = Path(review_dir).resolve()
    inbox.mkdir(parents=True, exist_ok=True)
    run_id = _run_id(inbox, review, profile_id)
    record_path = inbox / RUNS_DIR / f"{run_id}.json"
    if record_path.exists():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("status") == "complete":
            return {**record, "resumed": True}

    record = {
        "pipeline_version": PIPELINE_VERSION,
        "run_id": run_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile_id,
        "inbox": str(inbox),
        "review": str(review),
        "stages": {},
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    try:
        record["stages"]["provenance"] = provenance.provenance(inbox, profile_id)
        record["stages"]["year"] = year.apply_year(inbox, id_year=id_year)
        record["stages"]["route"] = route.route_to_review(inbox, review)
        record["audits"] = {
            "acquire": acquire.audit(inbox),
            "provenance": provenance.audit(inbox),
        }
        if any(record["audits"]["acquire"].values()) or any(record["audits"]["provenance"].values()):
            raise RuntimeError("inbox integrity audit failed")
        record["status"] = "complete"
        record["completed_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        record_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    return {**record, "resumed": False}


def audit(inbox_dir) -> dict:
    """Combined authoritative-ledger and sidecar audit."""
    return {"acquire": acquire.audit(inbox_dir),
            "provenance": provenance.audit(inbox_dir)}
