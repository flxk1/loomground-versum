"""Versum ingestion Pass 3: route everything to review, never shelve by guess.

Product layer, OUTSIDE the versum engine. Moves each provenance-settled artifact (and its
sidecar) from the inbox to the workspace **review queue**. It names no domain and knows no
shelf, so it cannot auto-file: a document reaches a domain/year folder only by a later,
measured, confidence-gated pass — never from here. This is the ``_review``-only intake that
guarantees the Level-1 product bar (provenance + dedup + stable URN) without risking a
misfile.

Also provides two seams that carry no policy of their own:
  * :func:`consolidation_plan` — a dry-run manifest of what an *existing* inbox folder would
    yield if drained through the pipeline (it moves nothing);
  * :func:`producer_ingest` — the one entry point a feed (e.g. a digest producer) calls to
    hand a file or URL to the same acquire path, so every producer shares one registration.

Idempotent: an artifact already in the review queue is a no-op on re-run. No network.
"""
from __future__ import annotations

import csv
from pathlib import Path

from . import acquire as _acquire
from .provenance import sidecar_path, SIDE


def route_to_review(inbox, review_dir) -> dict:
    """Move every acquired artifact that has a provenance sidecar into ``review_dir``.

    Returns counts in {routed, skipped_no_sidecar, already_routed}. Never writes a domain
    folder; the review queue is the only destination.
    """
    inbox = Path(inbox)
    review = Path(review_dir)
    review.mkdir(parents=True, exist_ok=True)
    counts = {"routed": 0, "skipped_no_sidecar": 0, "already_routed": 0}
    outcomes = []

    log = _acquire.load_log(inbox)
    for row in log:
        if row.get("status") not in {"registered", "review"}:
            continue
        name = row.get("artifact") or ""
        if not name:
            continue
        src = inbox / name
        dest = review / name
        sc = sidecar_path(inbox, name)
        review_sc = review / (name + SIDE)

        if dest.exists():
            # Resume an interrupted two-file move by carrying the sidecar forward.
            if sc.exists() and not review_sc.exists():
                sc.replace(review_sc)
            if review_sc.exists():
                row.update(status="review", location=str(dest))
                counts["already_routed"] += 1
                outcomes.append({"artifact": name, "outcome": "already_routed"})
            else:
                counts["skipped_no_sidecar"] += 1
                outcomes.append({"artifact": name, "outcome": "skipped_no_sidecar"})
            continue
        if not src.exists() or not sc.exists():
            counts["skipped_no_sidecar"] += 1
            outcomes.append({"artifact": name, "outcome": "skipped_no_sidecar"})
            continue

        src.replace(dest)
        sc.replace(review_sc)
        row.update(status="review", location=str(dest))
        counts["routed"] += 1
        outcomes.append({"artifact": name, "outcome": "routed", "urn": row.get("urn")})
    _acquire.save_log(inbox, log)
    return {"counts": counts, "outcomes": outcomes}


def consolidation_plan(old_inbox_dirs, out_csv) -> list[dict]:
    """Dry-run: enumerate files under existing inbox folders into a reviewable plan. Moves nothing.

    Each row: ``source_path, filename, size_bytes, proposed_action, has_sidecar`` (action is
    always ``acquire`` — the plan proposes intake, never a shelf). Excludes dotfiles and
    ``_``-prefixed infra. A ``*.metadata.json`` provenance sidecar is NOT an independent input:
    it travels with its artifact, so it is skipped and flagged on the artifact's row instead —
    so a pre-sidecar-ed inbox is drained without double-processing or re-minting.
    """
    from .provenance import SIDE
    rows: list[dict] = []
    for d in old_inbox_dirs:
        root = Path(d)
        if not root.exists():
            continue
        for f in sorted(root.rglob("*")):
            if not f.is_file():
                continue
            if any(part.startswith("_") or part.startswith(".") for part in f.relative_to(root).parts):
                continue
            if f.name.endswith(SIDE):
                continue                                   # a sidecar is not a separate input
            rows.append({"source_path": str(f), "filename": f.name,
                         "size_bytes": f.stat().st_size, "proposed_action": "acquire",
                         "has_sidecar": (f.parent / (f.name + SIDE)).exists()})
    out = Path(out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["source_path", "filename", "size_bytes",
                                           "proposed_action", "has_sidecar"])
        w.writeheader()
        w.writerows(rows)
    return rows


def producer_ingest(item, inbox, profile_id: str = "generic", namespace=None, fetcher=None) -> dict:
    """One shared intake for any producer (feed, watcher, manual drop): hand a file path or a
    URL to the acquire path. A thin, documented seam so every producer registers identically.
    """
    return _acquire.acquire(item, inbox, profile_id=profile_id, namespace=namespace, fetcher=fetcher)
