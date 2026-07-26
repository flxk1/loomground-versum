"""Versum ingestion Pass 1: pin identity, deduplicate, sidecar, and quarantine.

Product layer, OUTSIDE the versum engine (no domain vocabulary, no governance surface). Takes
the artifacts a Pass-0 acquire has placed in the inbox and, for each, settles the provenance
record the indexer will later join on:

  * the URN is fixed from the file's **content or canonical id**, never from where the file
    sits — so a later move to a shelf cannot change it;
  * an unreadable, empty, or structurally-broken file is quarantined in ``_failed/`` with a
    recorded reason instead of being registered;
  * identical bytes collapse to one record (the content URN is the same), so a duplicate is
    logged, not registered twice;
  * a ``<artifact>.metadata.json`` sidecar carrying ``canonical_urn`` is written next to the
    artifact — the inbox counterpart to a registry row, the form :func:`versum.io.consume.read_sidecars`
    reads, so the engine reuses this identity rather than minting a parallel one.

Idempotent: a re-run whose sidecar already matches the bytes writes nothing. Reads the acquire
ledger for the settled URN and source URL; it does not walk raw directory contents, so a README
or a stray file is never mistaken for an acquired artifact. No network.
"""
from __future__ import annotations

import json
from pathlib import Path

from versum.identity.core import content_sha256, deterministic_identity
from versum.profile import get_profile
import versum.profiles  # noqa: F401 — register built-in profiles

from . import acquire as _acquire

SIDE = ".metadata.json"
FAILED_DIR = "_failed"
FAILED_LOG = "_failed/_failed_log.csv"

# identity method (engine rung) -> provenance level recorded in the sidecar.
_LEVEL = {"content-sha256": "content", "pdf-title": "title", "path-slug": "filename"}

# structural sniff: a magic-byte prefix an extension must carry to be admissible.
_MAGIC = {".pdf": b"%PDF"}


def sidecar_path(inbox, artifact_name: str) -> Path:
    return Path(inbox) / (artifact_name + SIDE)


def _level_for(method: str) -> str:
    # any profile-supplied canonical scheme is neither a fallback rung nor a title.
    return _LEVEL.get(method, "canonical")


def _looks_broken(path: Path) -> str | None:
    """Return a reason string if the file cannot be admitted, else ``None``."""
    try:
        size = path.stat().st_size
    except OSError:
        return "unreadable"
    if size == 0:
        return "empty"
    magic = _MAGIC.get(path.suffix.lower())
    if magic is not None:
        try:
            with open(path, "rb") as fh:
                head = fh.read(len(magic))
        except OSError:
            return "unreadable"
        if head != magic:
            return f"not-a-{path.suffix.lower().lstrip('.')}"
    return None


def _quarantine(inbox: Path, artifact: Path, reason: str) -> Path:
    failed = inbox / FAILED_DIR
    failed.mkdir(parents=True, exist_ok=True)
    dest = failed / artifact.name
    if artifact.resolve() != dest.resolve():
        artifact.replace(dest)
    log = inbox / FAILED_LOG
    new = not log.exists()
    with open(log, "a", encoding="utf-8") as fh:
        if new:
            fh.write("artifact,reason\n")
        fh.write(f"{artifact.name},{reason}\n")
    return dest


def provenance(inbox, profile_id: str = "generic", namespace=None) -> dict:
    """Settle provenance for every acquired artifact in ``inbox``. Idempotent.

    Returns counts and the per-artifact outcome in {registered, duplicate, failed, unchanged}.
    """
    inbox = Path(inbox)
    profile = get_profile(profile_id)
    ns = namespace or profile.namespace
    log = _acquire.load_log(inbox)

    seen_urn: dict[str, str] = {}      # canonical_urn -> first artifact that claimed it
    outcomes: list[dict] = []
    counts = {"registered": 0, "duplicate": 0, "failed": 0, "unchanged": 0}

    # pre-seed seen_urn from sidecars already on disk so a re-run is a no-op and dedup holds.
    for sc in sorted(inbox.glob("*" + SIDE)):
        try:
            d = json.loads(sc.read_text(encoding="utf-8"))
        except Exception:
            continue
        urn = (d.get("canonical_urn") or "").strip()
        if urn:
            seen_urn.setdefault(urn, sc.name[:-len(SIDE)])

    for row in log:
        if row.get("status") not in {"acquired", "registered"}:
            continue
        name = row.get("artifact") or ""
        artifact = inbox / name
        if not name or not artifact.exists():
            continue

        reason = _looks_broken(artifact)
        if reason:
            dest = _quarantine(inbox, artifact, reason)
            sidecar_path(inbox, name).unlink(missing_ok=True)
            row.update(status="failed", location=str(dest), failure_reason=reason,
                       quarantine_path=str(dest))
            counts["failed"] += 1
            outcomes.append({"artifact": name, "outcome": "failed", "reason": reason})
            continue

        # Pass 0 owns identity. Provenance verifies its bytes and records the settled identity;
        # it must never re-mint from the content-addressed artifact filename.
        sha = content_sha256(artifact) or ""
        expected_sha = (row.get("content_sha256") or "").strip()
        if expected_sha and expected_sha != sha:
            reason = "content-digest-mismatch"
            dest = _quarantine(inbox, artifact, reason)
            sidecar_path(inbox, name).unlink(missing_ok=True)
            row.update(status="failed", location=str(dest), failure_reason=reason,
                       quarantine_path=str(dest))
            counts["failed"] += 1
            outcomes.append({"artifact": name, "outcome": "failed", "reason": reason})
            continue
        urn = (row.get("urn") or "").strip()
        if not urn:  # legacy ledger only: settle once, then persist below
            urn, ident, method, title, verif = deterministic_identity(
                artifact, profile, namespace=ns)
        else:
            ident = (row.get("identifier") or urn.rsplit(":", 1)[-1]).strip()
            method = (row.get("identity_method") or "unknown").strip()
            title = (row.get("title") or artifact.stem).strip()
            verif = (row.get("verification") or
                     ("content" if method == "content-sha256" else "provenance-ledger"))

        sc = sidecar_path(inbox, name)
        if sc.exists():
            try:
                prev = json.loads(sc.read_text(encoding="utf-8"))
            except Exception:
                prev = {}
            if prev.get("canonical_urn") == urn and prev.get("sha256") == sha:
                row.update(status="registered", location=name, content_sha256=sha,
                           failure_reason="", quarantine_path="")
                counts["unchanged"] += 1
                outcomes.append({"artifact": name, "outcome": "unchanged", "urn": urn})
                continue

        first = seen_urn.get(urn)
        if first and first != name:
            duplicates = inbox / "_duplicates"
            duplicates.mkdir(parents=True, exist_ok=True)
            dest = duplicates / artifact.name
            artifact.replace(dest)
            row.update(status="duplicate", location=str(dest), duplicate_of=first)
            counts["duplicate"] += 1
            outcomes.append({"artifact": name, "outcome": "duplicate",
                             "urn": urn, "duplicate_of": first})
            continue

        sidecar = {
            "canonical_urn": urn,
            "identifier": ident,
            "identity_method": method,
            "provenance_level": _level_for(method),
            "title": title,
            "verification": verif,
            "sha256": sha,
            "source_file": name,
            "source_url": row.get("source_url", "") or "",
        }
        sc.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
        row.update(status="registered", location=name, content_sha256=sha,
                   failure_reason="", quarantine_path="")
        seen_urn.setdefault(urn, name)
        counts["registered"] += 1
        outcomes.append({"artifact": name, "outcome": "registered", "urn": urn,
                         "provenance_level": sidecar["provenance_level"]})

    _acquire.save_log(inbox, log)
    return {"counts": counts, "outcomes": outcomes}


def read_sidecar(inbox, artifact_name: str) -> dict | None:
    p = sidecar_path(inbox, artifact_name)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def audit(inbox) -> dict:
    """Both-directions: every registered sidecar has its artifact, and every acquired,
    non-quarantined artifact has a sidecar. Empty lists == clean.
    """
    inbox = Path(inbox)
    orphan_sidecars, missing_sidecars = [], []
    for sc in sorted(inbox.glob("*" + SIDE)):
        stub = sc.name[:-len(SIDE)]
        if not (inbox / stub).exists():
            orphan_sidecars.append(sc.name)
    log = _acquire.load_log(inbox)
    for row in log:
        if row.get("status") not in {"acquired", "registered"}:
            continue
        name = row.get("artifact") or ""
        if name and (inbox / name).exists() and not sidecar_path(inbox, name).exists():
            missing_sidecars.append(name)
    return {"orphan_sidecars": orphan_sidecars, "missing_sidecars": missing_sidecars}
