"""Versum ingestion Pass 0: acquire a file or URL into a workspace inbox.

Product layer, OUTSIDE the versum engine (no domain vocabulary, no governance surface). Turns
one dropped file or one submitted URL into either:

  * a local **artifact** placed in the inbox (ready for Pass-1 provenance), or
  * a **citation-only** record in ``_pending_fetch/`` when the bytes cannot be had yet.

Identity is fixed at acquire time and is NEVER derived from the shelf path:

  * a **canonical id in the URL** (any scheme the active profile recognises) wins, fetch or
    no fetch, so the same source keeps ONE urn across the fetch boundary;
  * a **fetched artifact** with no canonical id keys on its content hash (engine rung 2);
  * an **unreachable URL** with no canonical id keys on a normalised-URL slug — a stable
    placeholder, upgraded to the canonical/content urn once the artifact arrives.

The network is **injected** (a ``Fetcher``), never imported — the engine's no-network rule
holds and these paths run offline. Idempotent: re-submitting an already-acquired input is a
no-op; a citation whose artifact later arrives is *upgraded in place* (same urn, content hash
recorded additively — the identity is not replaced).
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import hashlib
import urllib.parse
from pathlib import Path, PureWindowsPath

from versum.identity.core import content_sha256, deterministic_identity
from versum.profile import get_profile
import versum.profiles  # noqa: F401 — register built-in profiles

LOG_NAME = "_acquire_log.csv"
PENDING_DIR = "_pending_fetch"
LOG_COLUMNS = [
    "input", "kind", "urn", "previous_urn", "identifier", "identity_method",
    "status", "artifact", "location", "source_url", "content_sha256", "title",
    "verification", "failure_reason", "quarantine_path", "duplicate_of",
]

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _slug(s: str, maxlen: int = 80) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:maxlen]


def is_url(item) -> bool:
    return isinstance(item, str) and bool(_URL_RE.match(item))


# ── identity from a URL ──────────────────────────────────────────
def canonical_from_url(url: str, profile, namespace: str):
    """``(urn, scheme, ident)`` if the URL carries a profile-known id, else ``None``.

    Uses the SAME identifier patterns the engine applies to filenames/metadata, so a URL and
    the artifact it later yields resolve to the identical canonical urn.
    """
    hay = urllib.parse.unquote(url)
    for scheme, pattern in profile.source_identifiers:
        m = pattern.search(hay)
        if m:
            ident = m.group(1).lower().rstrip(".")
            return (f"urn:{namespace}:{scheme}:{ident}", scheme, ident)
    return None


def url_placeholder_urn(url: str, namespace: str) -> str:
    """A stable, path-independent placeholder for an ungrounded URL (host+path, no scheme/query)."""
    parts = urllib.parse.urlsplit(url)
    base = (parts.netloc + parts.path).rstrip("/")
    return f"urn:{namespace}:url:{_slug(base)}"


def _fully_unquote(value: str) -> str:
    """Decode nested URL quoting to a fixed point.

    A second decoding pass must not be able to turn a filename accepted here into a path
    separator or dot segment later.
    """
    for _ in range(len(value) + 1):
        decoded = urllib.parse.unquote(value)
        if decoded == value:
            return decoded
        value = decoded
    raise ValueError("URL artifact name has excessive nested encoding")


def _basename_from_url(url: str, fallback: str) -> str:
    base = _fully_unquote(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1])
    base = base.strip()
    if "\x00" in base:
        raise ValueError("URL artifact name contains a NUL byte")
    if "/" in base or "\\" in base:
        raise ValueError("URL artifact name contains a path separator")
    if Path(base).is_absolute() or PureWindowsPath(base).is_absolute() or PureWindowsPath(base).drive:
        raise ValueError("URL artifact name is absolute")
    if base in (".", ".."):
        raise ValueError("URL artifact name is a dot segment")
    return base if base and base not in (".", "..") else fallback


def _url_destination(inbox: Path, name: str) -> Path:
    """Return a URL artifact destination only when it resolves inside ``inbox``.

    Resolving the not-yet-created leaf also follows an existing leaf symlink, preventing a
    content-addressed filename planted as a symlink from redirecting the write.
    """
    root = inbox.resolve()
    destination = (inbox / name).resolve(strict=False)
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise ValueError("URL artifact destination escapes the configured inbox") from exc
    return destination


def _content_name(basename: str, sha: str) -> str:
    """Content-addressed artifact filename: ``<sha[:12]>-<basename>``.

    Prefixing with the content hash makes the on-disk name collision-free — two different
    documents that share a basename get different files (different bytes → different sha),
    while re-acquiring the same bytes maps to the same name (idempotent overwrite).
    """
    return f"{sha[:12]}-{basename}" if sha else basename


def _local_name(inbox: Path, basename: str, sha: str) -> str:
    """Keep a local artifact's original name unless that name is already occupied.

    Canonical identity remains content-addressed. The hash prefix is a collision escape for
    two different files sharing a basename, not a mandatory user-visible rename.
    """
    plain = inbox / basename
    return basename if not plain.exists() else _content_name(basename, sha)


# ── fetcher seam (injected; never imported) ──────────────────────
class Fetcher:
    """Fetch a URL's bytes, or ``None`` when unreachable. Implementations live device-side."""

    def fetch(self, url: str) -> bytes | None:  # pragma: no cover - interface
        raise NotImplementedError


class NullFetcher(Fetcher):
    """Never fetches — every URL degrades to citation-only. The safe default."""

    def fetch(self, url: str) -> bytes | None:
        return None


# ── the acquire ledger (a staging manifest, NOT a second authoritative registry) ──
def _log_path(inbox) -> Path:
    return Path(inbox) / LOG_NAME


def load_log(inbox) -> list[dict]:
    p = _log_path(inbox)
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def save_log(inbox, rows) -> None:
    p = _log_path(inbox)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _citation_path(inbox, urn: str) -> Path:
    return Path(inbox) / PENDING_DIR / (_slug(urn) + ".citation.json")


# ── the acquire pass ─────────────────────────────────────────────
def acquire(item, inbox, profile_id: str = "generic", namespace=None, fetcher: Fetcher = None) -> dict:
    """Acquire ONE item — a local file path, or a ``str`` URL — into ``inbox``. Idempotent.

    Returns a dict with ``status`` in {acquired, citation-only, upgraded, duplicate} and the
    settled ``urn``. See the module docstring for the identity rules.
    """
    profile = get_profile(profile_id)
    ns = namespace or profile.namespace
    inbox = Path(inbox)
    inbox.mkdir(parents=True, exist_ok=True)
    log = load_log(inbox)
    by_urn = {r["urn"]: r for r in log}
    by_input = {r.get("input", ""): r for r in log}
    fetcher = fetcher or NullFetcher()

    if is_url(item):
        url = item
        canon = canonical_from_url(url, profile, ns)
        # Canonical, already seen, no upgrade possible without bytes → short-circuit (no fetch).
        if (canon and canon[0] in by_urn
                and by_urn[canon[0]]["status"] in {"acquired", "registered", "review"}):
            return {"status": "duplicate", "urn": canon[0]}

        data = fetcher.fetch(url)

        if data is not None:
            # Hash the bytes in memory FIRST — the urn and the dedup decision are made before
            # anything is written to disk, so a duplicate never leaves a stray artifact.
            sha = hashlib.sha256(data).hexdigest()
            if canon:
                urn, method, identifier = canon
            else:
                urn, method, identifier = f"urn:{ns}:sha256:{sha}", "content-sha256", sha
            name = _content_name(_basename_from_url(url, _slug(canon[2]) if canon else "artifact"), sha)
            destination = _url_destination(inbox, name)
            existing = by_urn.get(urn) or by_input.get(url)
            if existing:
                if existing["status"] == "citation-only":
                    # The pending citation is the same input even when its placeholder URN must
                    # now transition to a content URN. Keep the former identity as an alias.
                    old_urn = existing["urn"]
                    destination.write_bytes(data)
                    existing.update(
                        urn=urn, previous_urn=old_urn if old_urn != urn else "",
                        identifier=identifier, identity_method=method, status="acquired",
                        artifact=name, location=name, content_sha256=sha,
                        verification="source-url" if canon else "content",
                        failure_reason="", quarantine_path="",
                    )
                    _citation_path(inbox, old_urn).unlink(missing_ok=True)
                    save_log(inbox, log)
                    return {"status": "upgraded", "urn": urn, "artifact": name}
                if existing["status"] in {"acquired", "registered", "review"}:
                    return {"status": "duplicate", "urn": urn}   # no write → no orphan
                if existing["status"] == "failed":
                    destination.write_bytes(data)
                    existing.update(
                        identifier=identifier, identity_method=method, status="acquired",
                        artifact=name, location=name, content_sha256=sha,
                        verification="source-url" if canon else "content",
                        failure_reason="", quarantine_path="",
                    )
                    save_log(inbox, log)
                    return {"status": "acquired", "urn": urn, "artifact": name}
            destination.write_bytes(data)
            row = {"input": url, "kind": "url", "urn": urn, "previous_urn": "",
                   "identifier": identifier, "identity_method": method,
                   "status": "acquired", "artifact": name, "location": name,
                   "source_url": url, "content_sha256": sha, "title": name,
                   "verification": "source-url" if canon else "content",
                   "failure_reason": "", "quarantine_path": ""}
        else:
            urn, method, identifier = (canon if canon else
                                       (url_placeholder_urn(url, ns), "url-slug", ""))
            if urn in by_urn:
                return {"status": "duplicate", "urn": urn}
            cp = _citation_path(inbox, urn)
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps({"urn": urn, "source_url": url,
                                      "identity_method": method, "status": "pending_fetch"},
                                     ensure_ascii=False, indent=2), encoding="utf-8")
            row = {"input": url, "kind": "url", "urn": urn, "previous_urn": "",
                   "identifier": identifier, "identity_method": method,
                   "status": "citation-only", "artifact": "", "location": str(cp),
                   "source_url": url, "content_sha256": "", "title": "",
                   "verification": "source-url", "failure_reason": "",
                   "quarantine_path": ""}
    else:
        p = Path(item)
        urn, ident, method, title, verif = deterministic_identity(p, profile, namespace=ns)
        sha = content_sha256(p) or ""
        if urn in by_urn and by_urn[urn]["status"] in {"acquired", "registered", "review"}:
            return {"status": "duplicate", "urn": urn}   # dedup BEFORE copy → no stray file
        name = _local_name(inbox, p.name, sha)
        dest = inbox / name
        if p.resolve() != dest.resolve():
            shutil.copy2(p, dest)
        existing = by_urn.get(urn)
        if existing and existing.get("status") == "failed":
            existing.update(
                input=str(p), identifier=ident, identity_method=method, status="acquired",
                artifact=name, location=name, content_sha256=sha, title=title,
                verification=verif, failure_reason="", quarantine_path="",
            )
            save_log(inbox, log)
            return {"status": "acquired", "urn": urn, "method": method, "artifact": name}
        row = {"input": str(p), "kind": "file", "urn": urn, "previous_urn": "",
               "identifier": ident, "identity_method": method, "status": "acquired",
               "artifact": name, "location": name, "source_url": "",
               "content_sha256": sha, "title": title, "verification": verif,
               "failure_reason": "", "quarantine_path": ""}

    log.append(row)
    save_log(inbox, log)
    return {"status": row["status"], "urn": urn, "method": row["identity_method"],
            "artifact": row["artifact"]}


def audit(inbox) -> dict:
    """Both-directions integrity: no ledger row without its artifact/citation on disk, and no
    acquired artifact on disk without a ledger row. Returns lists of any orphans (empty == clean).
    """
    inbox = Path(inbox)
    log = load_log(inbox)
    orphan_rows = []
    for r in log:
        if r["status"] in {"acquired", "registered"}:
            location = Path(r.get("location") or r["artifact"])
            path = location if location.is_absolute() else inbox / location
            if not path.exists():
                orphan_rows.append(r["urn"])
        elif r["status"] == "citation-only":
            if not _citation_path(inbox, r["urn"]).exists():
                orphan_rows.append(r["urn"])
        elif r["status"] == "failed":
            location = r.get("quarantine_path") or ""
            if not location or not Path(location).exists():
                orphan_rows.append(r["urn"])
        elif r["status"] == "review":
            location = r.get("location") or ""
            if not location or not Path(location).exists():
                orphan_rows.append(r["urn"])
        elif r["status"] == "duplicate":
            location = r.get("location") or ""
            if not location or not Path(location).exists():
                orphan_rows.append(r["urn"])
    logged = {r["artifact"] for r in log
              if r["status"] in {"acquired", "registered"} and r["artifact"]}
    orphan_files = [f.name for f in inbox.iterdir()
                    if (f.is_file() and not f.name.startswith("_")
                        and not f.name.endswith(".metadata.json") and f.name not in logged)]
    return {"orphan_rows": orphan_rows, "orphan_files": orphan_files}
