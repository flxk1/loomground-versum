"""versum/write.py — the guard at the door of the Versum.

A **deterministic Python pipeline** — the single write path into a Versum graph. Given
one source *or* a whole folder it:

  1. resolves the source's **identity** → a canonical URN (a well-known identifier that
     the active profile knows how to recognise, from the filename or PDF metadata; else a
     title/path slug),
  2. **dedups** against the folder's source registry (by URN, by content hash, by title),
  3. writes a **house stub + metadata sidecar** (records the canonical URN so the indexer
     honours it),
  4. **indexes** the folder into candidate claims + fingerprints.

No LLM is called on the happy path. Identity that the deterministic rung can't settle can
be escalated through a **resolver ladder** — a local model first, a hosted model only
after — but the ladder is optional and injected; nothing here imports a model. This is the
router from the manifest, made real: nothing enters the Versum except through this gate.

**No network, ever.** This pipeline operates only on files already on disk; it never
fetches a PDF or any binary. Binary acquisition is out-of-band — a file the user supplies,
or the corpus's own downloader run in the user's environment. A source with no local PDF
is recorded at the provenance layer (stub + sidecar); its claims are built later, once the
PDF has arrived out-of-band.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .store import graph as g
from . import profiles as _profiles  # noqa: F401 — register built-ins
from .identity.core import FALLBACK_METHODS, deterministic_identity
from .store.index import SUPPORTED, PDF_EXT, TEXT_EXT, index_folder
from .profile import get_profile

# The .versum source registry REFERENCES the KG registry via ``library`` + ``canonical_urn``
# (Phase 1 reschema): it links back to the 19-column KG registry, never shadows it.
REGISTRY_COLUMNS = ["urn", "identifier", "identity_method", "sha1",
                    "title", "stub", "path", "verification", "library", "canonical_urn"]

# The identifier schemes a source may carry (rung 0) are supplied by the active profile
# (``profile.source_identifiers``) — the core names none of them. Year is a neutral,
# purely presentational cue used only to name the house stub.
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


class CaptureError(Exception):
    """A stable, user-facing source-admission failure."""

    def __init__(self, code: str, message: str, *, exit_code: int = 2):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def _validated_source(path, profile_id: str):
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise CaptureError("source_not_found", f"source does not exist: {source}", exit_code=3)
    if not source.is_file():
        raise CaptureError("source_not_file", f"source is not a file: {source}", exit_code=3)
    if source.suffix.lower() not in SUPPORTED:
        raise CaptureError(
            "unsupported_type",
            f"unsupported source type {source.suffix or '<none>'}; supported: {sorted(SUPPORTED)}",
            exit_code=4,
        )
    try:
        profile = get_profile(profile_id)
    except KeyError as exc:
        raise CaptureError("invalid_profile", f"unknown profile: {profile_id}", exit_code=4) from exc
    try:
        if source.suffix.lower() in TEXT_EXT:
            text = source.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                raise CaptureError("empty_source", f"source contains no text: {source}", exit_code=5)
        else:
            # Opening the PDF here prevents a malformed binary from entering the registry.
            import pdfplumber
            with pdfplumber.open(str(source)) as pdf:
                if not pdf.pages:
                    raise CaptureError("empty_source", f"PDF has no pages: {source}", exit_code=5)
    except CaptureError:
        raise
    except (OSError, UnicodeError) as exc:
        raise CaptureError("unreadable_source", f"cannot read source: {source}", exit_code=5) from exc
    except Exception as exc:
        raise CaptureError("extraction_failure", f"cannot parse source: {source}", exit_code=5) from exc
    return source, profile


def _materialize_source(source: Path, folder: Path, sha1: str) -> Path:
    """Copy an external source into the target without overwriting another file."""
    folder.mkdir(parents=True, exist_ok=True)
    try:
        source.relative_to(folder)
        return source
    except ValueError:
        pass
    destination = folder / source.name
    if destination.exists():
        if destination.is_file() and content_hash(destination) == sha1:
            return destination
        destination = folder / f"{sha1[:12]}-{source.name}"
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination


@dataclass
class Identity:
    urn: str
    identifier: str          # the bare id (a profile identifier scheme, or a slug)
    method: str              # <scheme from the profile> | pdf-title | content-sha256 | path-slug
    title: str
    verification: str        # metadata | content | filename


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _pdf_meta(path: Path) -> dict:
    if path.suffix.lower() not in PDF_EXT:
        return {}
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            return dict(pdf.metadata or {})
    except Exception:
        return {}


def resolve_identity(path, profile, resolver=None, namespace=None) -> Identity:
    """Deterministic identity resolution (rung 0), via the ONE shared resolver. Optionally
    escalate via a ladder.

    Rung-0 resolution is ``identity.deterministic_identity`` — the *same* function the
    indexer calls — so capture and index assign a file byte-identical URNs (ADR-URN, option
    A), for canonical-id files (resolved by a profile identifier scheme) as well as plain
    ones. ``resolver`` (if given) is called only when identity landed on a degraded fallback
    (content-hash or filename — see ``identity.FALLBACK_METHODS``); the happy path (a canonical
    scheme or a title) never calls it. ``namespace`` (loop 8) overrides the profile namespace
    when the source belongs to a library with its own ``urn_namespace``.
    """
    p = Path(path)
    meta = _pdf_meta(p)
    urn, ident, method, title, verif = deterministic_identity(
        p, profile, meta, namespace=namespace)
    if method not in FALLBACK_METHODS:
        return Identity(urn, ident, method, title, verif)
    # identity landed on a degraded fallback (content-hash or filename) → ambiguous.
    # Escalate through the ladder if one is wired.
    if resolver is not None:
        import urllib.parse
        name = urllib.parse.unquote(p.name)
        r = resolver({"path": str(p), "name": name, "pdf_metadata": meta})
        if r and r.get("urn"):
            return Identity(r["urn"], r.get("identifier", ""), r.get("method", "ladder"),
                            r.get("title", title), "metadata")
    return Identity(urn, ident, method, title, verif)


def content_hash(path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── registry + dedup ─────────────────────────────────────────────
def _versum_dir(folder) -> Path:
    return Path(folder).resolve() / ".versum"


def load_registry(folder) -> list[dict]:
    reg = _versum_dir(folder) / "source_registry.csv"
    if not reg.exists():
        return []
    with open(reg, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def save_registry(folder, rows) -> None:
    reg = _versum_dir(folder) / "source_registry.csv"
    reg.parent.mkdir(parents=True, exist_ok=True)
    with open(reg, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=REGISTRY_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def dedup(registry, urn, sha1, title):
    """Return (reason, existing_row) if this source is already admitted, else None."""
    for r in registry:
        if r.get("sha1") and r["sha1"] == sha1:
            return ("duplicate_hash", r)
        if r.get("urn") == urn:
            return ("duplicate_urn", r)
        if title and r.get("title") and r["title"].strip().lower() == title.strip().lower():
            return ("duplicate_title", r)
    return None


def write_stub(folder, ident: Identity, path) -> str:
    """Write a house stub + metadata sidecar; return the stub filename."""
    v = _versum_dir(folder)
    (v / "stubs").mkdir(parents=True, exist_ok=True)
    year = (YEAR_RE.search(Path(path).name) or [""])[0] if YEAR_RE.search(Path(path).name) else ""
    base = "-".join(x for x in (year, _slug(ident.title)[:60] or ident.identifier) if x)
    stub = f"{base}.md"
    (v / "stubs" / stub).write_text(
        f"# {ident.title}\n\n- URN: `{ident.urn}`\n- identifier: `{ident.identifier}`\n"
        f"- source file: `{Path(path).name}`\n- verification: {ident.verification}\n",
        encoding="utf-8")
    sidecar = {
        "sidecar_canonical": ident.urn, "identifier": ident.identifier,
        "identity_method": ident.method, "title": ident.title,
        "verification": ident.verification, "source_file": Path(path).name,
    }
    (v / "stubs" / (stub + ".metadata.json")).write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    return stub


# ── the guard: single source, or a whole folder ─────────────────
def capture_file(path, folder, profile_id="generic", resolver=None, reindex=True,
                 namespace=None, consume=None, library=None) -> dict:
    """Admit ONE source into the folder's Versum. Deterministic; dedup-gated.

    Phase 1: when a ``consume`` registry already carries a ``canonical_urn`` for this file
    (matched by relpath/filename), that URN is REUSED rather than minted (ADR-URN option B);
    ``namespace`` overrides the mint namespace (loop 8); ``library`` is recorded as the
    provenance linkage back to the KG registry.
    """
    source, profile = _validated_source(path, profile_id)
    folder = Path(folder).expanduser().resolve()
    registry = load_registry(folder)
    rel = source
    try:
        rel = rel.relative_to(Path(folder).resolve()).as_posix()
    except ValueError:
        rel = source.name
    reg_urn = consume.reuse_urn(relpath=rel, filename=source.name) if consume else None
    if reg_urn:
        ident = resolve_identity(source, profile, resolver, namespace)
        ident = Identity(reg_urn, ident.identifier, "kg-registry", ident.title, "kg-registry")
    else:
        ident = resolve_identity(source, profile, resolver, namespace)
    sha1 = content_hash(source)
    hit = dedup(registry, ident.urn, sha1, ident.title)
    if hit and hit[0] in {"duplicate_urn", "duplicate_title"} and hit[1].get("sha1") != sha1:
        # Two distinct external sources may legitimately share a basename/title. Preserve
        # both by falling back to content identity rather than declaring a false duplicate.
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        namespace_prefix = profile.namespace.rstrip(":")
        ident = Identity(
            f"{namespace_prefix}:sha256:{digest}", digest, "content-sha256",
            ident.title, "content",
        )
        hit = dedup(registry, ident.urn, sha1, "")
    if hit:
        reason, existing = hit
        return {"status": "duplicate", "admitted": False, "reason": reason,
                "profile": profile_id, "source_path": str(source),
                "target_path": existing.get("path", ""), "urn": ident.urn,
                "existing_urn": existing.get("urn")}
    target = _materialize_source(source, folder, sha1)
    stub = write_stub(folder, ident, target)
    registry.append({"urn": ident.urn, "identifier": ident.identifier,
                     "identity_method": ident.method, "sha1": sha1,
                     "title": ident.title, "stub": stub, "path": target.relative_to(folder).as_posix(),
                     "verification": ident.verification, "library": library or "",
                     "canonical_urn": reg_urn or ""})
    save_registry(folder, registry)
    stub_path = _versum_dir(folder) / "stubs" / stub
    result = {
        "status": "admitted", "admitted": True, "profile": profile_id,
        "source_path": str(source), "target_path": str(target), "urn": ident.urn,
        "method": ident.method, "title": ident.title, "stub": stub,
        "stub_path": str(stub_path), "sidecar_path": str(stub_path) + ".metadata.json",
    }
    if reindex:
        result["index"] = index_folder(folder, profile_id, namespace=namespace,
                                       consume=consume, library=library)
        claims = g.load_claims(_versum_dir(folder) / "claims.csv")
        result["claim_count"] = sum(row.get("source_urn") == ident.urn for row in claims)
        fingerprints = json.loads((_versum_dir(folder) / "fingerprints.json").read_text(
            encoding="utf-8"))
        result["fingerprint"] = fingerprints.get(ident.urn, {})
    return result


def capture_folder(folder, profile_id="generic", resolver=None,
                   namespace=None, consume=None, library=None) -> dict:
    """Admit every not-yet-admitted supported file under ``folder`` through the guard.

    Idempotent: a file already in the registry (by content hash) is passed over, so
    re-running after a document is dropped in admits ONLY the new document. Ends by
    rebuilding the claim/fingerprint index once. ``namespace`` / ``consume`` / ``library``
    are threaded through per Phase 1 (see :func:`capture_file`).
    """
    folder = Path(folder).resolve()
    admitted: list[dict] = []
    duplicates: list[dict] = []
    skipped: list[str] = []
    for p in sorted(folder.rglob("*")):
        if p.is_dir() or _versum_dir(folder) in p.parents:
            continue
        if any(part.startswith(".") for part in p.relative_to(folder).parts):
            continue
        if p.suffix.lower() not in SUPPORTED:
            skipped.append(p.relative_to(folder).as_posix())
            continue
        res = capture_file(p, folder, profile_id, resolver, reindex=False,
                           namespace=namespace, consume=consume, library=library)
        (admitted if res["admitted"] else duplicates).append(
            {"path": p.relative_to(folder).as_posix(), **res})
    index = index_folder(folder, profile_id, namespace=namespace,
                         consume=consume, library=library)
    return {"folder": str(folder), "profile": profile_id,
            "n_admitted": len(admitted), "n_duplicates": len(duplicates),
            "n_skipped": len(skipped), "admitted": admitted,
            "duplicates": duplicates, "skipped": skipped, "index": index}
