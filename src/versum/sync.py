"""versum/sync.py — the Live Index: incremental, config-driven indexing of libraries.

A UNIVERSAL, domain-neutral capability: point it at one or more library roots (via a JSON
config) and every file ADDED to a library after the initial bulk migration gets indexed
into the by-domain knowledge-graph store incrementally — one source at a time, append-only,
idempotent, reversible.

Design:

  * **Reuse, never duplicate.** Identity comes from :mod:`versum.identity.core` /
    :mod:`versum.io.consume` (reuse a registered ``canonical_urn`` or mint deterministically),
    extraction from :func:`versum.store.index._extract_file`, and the fingerprint from
    :mod:`versum.identity.fingerprint`. This module wires those built parts to a by-domain
    writer; it re-implements none of them.
  * **Append-only / reversible.** The corpus is never touched — files are only READ. The KG
    is written additively: a NEW file appends its rows; a CHANGED file first drops its OWN
    prior rows (matched on its canonical key / relpath) then re-appends, so it never rewrites
    another source's rows; a REMOVED file's KG rows are dropped while the file on disk is left
    alone (the removal is recorded, not enacted on the corpus).
  * **Idempotent.** A ``_sync_state.json`` snapshot (size, mtime fast-path; sha1 on drift)
    lets a pass skip everything already indexed, so re-running with no change writes nothing.
  * **Config-driven / universal.** No user path, OS, or domain vocabulary is baked in — every
    root, namespace and registry is named by the config. Pure poll loop; no OS watch calls;
    no network.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import time
from pathlib import Path

from .io import consume
from . import profiles as _profiles  # noqa: F401 — registers built-in profiles
from .identity.fingerprint import fingerprint
from .store.graph import flatten_claim
from .identity.core import deterministic_identity
from .store.index import SUPPORTED, _extract_file, _json_safe
from .profile import get_profile
from .snapshot import mint_graph_version, stamp_graph_version
from .events import EventLog, object_digest, source_object_id

STATE_FILE = "_sync_state.json"
STATE_VERSION = 1
BY_DOMAIN = "by-domain"

# The by-domain claims table: a leading canonical_urn + library key, then the carried claim
# columns. No domain vocabulary is named — every value is carried through from the extractor.
CLAIM_COLUMNS = [
    "canonical_urn", "library", "item_id", "source_urn", "unit_id", "unit_type",
    "span_start", "span_end", "marker", "text", "polarity", "type", "predicate",
    "dimension", "modality", "quantification", "principle", "judicial_canon", "inference_rule",
    "confidence", "verification",
]
SOURCE_COLUMNS = ["source_urn", "path", "n_items", "unit_type", "profile", "provenance",
                  "library", "canonical_urn"]


# ── config ───────────────────────────────────────────────────────
def load_config(path) -> dict:
    """Load and normalise a Live Index config (universal JSON schema).

    Fills defaults (``profile_id``, ``exclude_prefixes``, ``watch_interval_seconds``) and
    propagates the top-level ``exclude_prefixes`` onto each library so :func:`plan` is
    self-contained. Per-library defaults: ``registry_csv=None``, ``registry_path_prefix=""``.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.setdefault("profile_id", "generic")
    data.setdefault("exclude_prefixes", ["_"])
    data.setdefault("watch_interval_seconds", 30)
    data.setdefault("libraries", [])
    data.setdefault("nd_systems", [])
    if data["nd_systems"]:
        from .nd import NDRegistry
        base = Path(path).resolve().parent
        paths = [str((base / p).resolve()) if not Path(p).is_absolute() else p
                 for p in data["nd_systems"]]
        data["_nd_registry"] = NDRegistry(include_core=True).load(paths)
    for lib in data["libraries"]:
        lib.setdefault("exclude_prefixes", data["exclude_prefixes"])
        lib.setdefault("registry_csv", None)
        lib.setdefault("registry_path_prefix", "")
        lib.setdefault("urn_namespace", None)
    return data


# ── change detection ─────────────────────────────────────────────
def content_sha1(path) -> str:
    """The SHA-1 of a file's raw bytes (streamed; no whole-file load)."""
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk(root: Path, exclude_prefixes) -> dict:
    """Map ``relpath -> {abspath, domain}`` for every supported file under ``root``.

    ``relpath`` is POSIX, relative to ``root``. ``domain`` is the first path component (or
    ``"_root"`` for a file directly under ``root``). A file inside a top-level subdirectory
    whose name starts with any ``exclude_prefix`` is skipped; files directly under ``root``
    (domain ``_root``) are never excluded by a prefix rule.
    """
    root = Path(root)
    prefixes = tuple(exclude_prefixes or ())
    out: dict = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in SUPPORTED:
            continue
        rel = p.relative_to(root).as_posix()
        parts = rel.split("/")
        if len(parts) > 1:
            top = parts[0]
            if any(top.startswith(pfx) for pfx in prefixes):
                continue
            domain = top
        else:
            domain = "_root"
        out[rel] = {"abspath": p, "domain": domain}
    return out


class SyncState:
    """The Live Index snapshot: ``<kg_root>/_sync_state.json``.

    ``files`` maps ``"<lib_id>::<relpath>"`` to
    ``{sha1, canonical_urn, size, mtime, domain, n_claims}``. Serialised sorted with no
    wall-clock timestamp of its own, so an unchanged pass rewrites byte-identical content.

    ``profile`` records the extraction profile the files were indexed under
    (K2: a profile change is a semantic change even when no source byte moved,
    so a pass under a different profile must re-extract, not fast-path).
    """

    def __init__(self, kg_root):
        self.path = Path(kg_root) / STATE_FILE
        self.version = STATE_VERSION
        self.files: dict = {}
        self.profile: dict | None = None
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.files = data.get("files", {}) or {}
            self.version = data.get("version", STATE_VERSION)
            self.profile = data.get("profile")

    @staticmethod
    def key(lib_id: str, relpath: str) -> str:
        return f"{lib_id}::{relpath}"

    def get(self, lib_id: str, relpath: str):
        return self.files.get(self.key(lib_id, relpath))

    def put(self, lib_id: str, relpath: str, entry: dict) -> None:
        self.files[self.key(lib_id, relpath)] = entry

    def remove(self, lib_id: str, relpath: str) -> None:
        self.files.pop(self.key(lib_id, relpath), None)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": self.version, "files": self.files,
                   "profile": self.profile}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")


def plan(library_cfg: dict, root, state: SyncState, force_changed=False) -> dict:
    """Classify a library's files vs the recorded state.

    Fast-path on ``(size, mtime)``; a SHA-1 is computed only when they drift or a file is
    new. Returns ``{"new", "changed", "removed", "unchanged_count"}`` with POSIX relpaths.
    ``removed`` are state keys for this library no longer present on disk.
    ``force_changed`` classifies every known file as changed regardless of
    content — used when the extraction profile changed, so byte-identical
    sources still re-extract.
    """
    lib_id = library_cfg["id"]
    root = Path(root)
    disk = _walk(root, library_cfg.get("exclude_prefixes", ["_"]))

    new, changed, unchanged = [], [], 0
    for rel in sorted(disk):
        entry = state.get(lib_id, rel)
        if entry is None:
            new.append(rel)
            continue
        if force_changed:
            changed.append(rel)
            continue
        st = disk[rel]["abspath"].stat()
        if int(st.st_mtime) == entry.get("mtime") and st.st_size == entry.get("size"):
            unchanged += 1
            continue
        if content_sha1(disk[rel]["abspath"]) == entry.get("sha1"):
            unchanged += 1  # touched (mtime moved) but content identical
        else:
            changed.append(rel)

    prefix = lib_id + "::"
    on_disk = set(disk)
    removed = [k[len(prefix):] for k in state.files
               if k.startswith(prefix) and k[len(prefix):] not in on_disk]
    return {"new": new, "changed": changed, "removed": sorted(removed),
            "unchanged_count": unchanged}


# ── the append-only by-domain writer ─────────────────────────────
def _read_rows(path: Path):
    """Return ``(fieldnames, rows)`` for a CSV, NUL-stripped and csv-safe, ``([],[])`` if absent."""
    import csv
    if not path.exists():
        return [], []
    raw = path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")
    r = csv.DictReader(io.StringIO(raw))
    rows = list(r)
    return list(r.fieldnames or []), rows


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temp file + :func:`os.replace`.

    A plain ``open(path, "w")`` that is interrupted (crash, full disk, a
    concurrent writer) leaves a truncated file behind. For a read-modify-write
    store like ``fingerprints.json`` that truncated file reads back as corrupt on
    the next pass and — before this was made atomic — was silently reset to an
    empty dict and overwritten, destroying every previously recorded entry.
    Writing to a sibling temp file and atomically renaming it into place means a
    reader only ever sees the whole old file or the whole new one, never a
    half-written one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _preserve_corrupt(path: Path) -> Path:
    """Rename an unparseable store aside as ``<name>.corrupt`` for inspection.

    Never clobbers an earlier backup — if ``.corrupt`` is taken, a numeric suffix
    is added — so repeated corruption can't erase the first (most useful) copy.
    Returns the path the file was preserved at.
    """
    dest = path.with_name(f"{path.name}.corrupt")
    n = 1
    while dest.exists():
        dest = path.with_name(f"{path.name}.corrupt.{n}")
        n += 1
    os.replace(path, dest)
    return dest


def _load_fingerprint_store(fp_path: Path, domain: str) -> dict:
    """Return the ``{canonical_urn: fingerprint}`` store, or ``{}`` if absent/empty.

    A store that exists, is non-empty, but does not parse as a JSON object is
    genuine corruption (a truncated write, disk damage, a concurrent writer). The
    old behavior silently reset it to ``{}`` and then overwrote the file, erasing
    every previously recorded fingerprint for the domain. Instead, preserve the
    unreadable file (``_preserve_corrupt``) and raise, so the caller fails this
    source loudly rather than destroying data. An empty/whitespace file is treated
    as "no entries yet", not corruption.
    """
    if not fp_path.exists():
        return {}
    text = fp_path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except Exception as e:
        kept = _preserve_corrupt(fp_path)
        raise ValueError(
            f"fingerprints store for domain {domain!r} is unparseable "
            f"({type(e).__name__}: {e}); preserved the unreadable file as "
            f"{kept.name} and aborted this source's write so existing fingerprints "
            f"are not destroyed"
        ) from e
    if not isinstance(data, dict):
        kept = _preserve_corrupt(fp_path)
        raise ValueError(
            f"fingerprints store for domain {domain!r} is not a JSON object "
            f"(found {type(data).__name__}); preserved it as {kept.name} and "
            f"aborted this source's write to avoid destroying existing data"
        )
    return data


def _write_rows(path: Path, columns, rows) -> None:
    import csv
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for row in rows:
        w.writerow({c: ("" if row.get(c) is None else row.get(c)) for c in columns})
    _atomic_write_text(path, buf.getvalue())


class KGStore:
    """Append-only writer for the by-domain KG store under ``<kg_root>/by-domain/<domain>/``.

    A source is a unit of work: :meth:`append_source` adds its claim rows, fingerprint and
    source row; :meth:`remove_source` drops exactly that source's prior rows (by its canonical
    key / relpath) so a changed or removed file never disturbs another source. All CSV I/O
    goes through the ``csv`` module (safe with embedded newlines/commas) and strips NUL bytes
    on read (some extracted PDF text carries them).
    """

    def __init__(self, kg_root):
        self.root = Path(kg_root)

    def _domain_dir(self, domain: str) -> Path:
        return self.root / BY_DOMAIN / domain

    def claim_ids(self, domain: str, canonical_urn: str) -> list[str]:
        """Return the stable claim IDs currently projected for one source."""
        _cols, rows = _read_rows(self._domain_dir(domain) / "claims.csv")
        return sorted(row.get("item_id", "") for row in rows
                      if row.get("canonical_urn") == canonical_urn and row.get("item_id"))

    def append_source(self, domain, library, canonical_urn, provenance, relpath, sha1,
                      claim_rows, fingerprint) -> None:
        """Append one source's rows to the by-domain store (create tables on first write)."""
        import csv
        d = self._domain_dir(domain)
        d.mkdir(parents=True, exist_ok=True)

        # fingerprints.json — read the existing {canonical_urn: fingerprint} store
        # FIRST, before writing anything. A store that exists but won't parse is
        # genuine corruption; _load_fingerprint_store preserves it and raises here,
        # so a bad read aborts the whole source (recorded in the run's error list)
        # instead of silently resetting to {} and overwriting away every prior
        # fingerprint for the domain. Reading before the claims append also means a
        # corrupt store fails the source cleanly, with no partial write left behind.
        fp_path = d / "fingerprints.json"
        fps = _load_fingerprint_store(fp_path, domain)

        # claims.csv — append (header once). Each row stamped with canonical_urn + library.
        claims_path = d / "claims.csv"
        fresh = not claims_path.exists()
        with open(claims_path, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=CLAIM_COLUMNS, extrasaction="ignore",
                               lineterminator="\n")
            if fresh:
                w.writeheader()
            for r in claim_rows:
                stamped = {"canonical_urn": canonical_urn, "library": library, **r}
                w.writerow({c: ("" if stamped.get(c) is None else stamped.get(c))
                            for c in CLAIM_COLUMNS})

        # fingerprints.json — modify the store read above and write it back
        # atomically so an interrupted write can't leave a truncated (corrupt) file.
        fps[canonical_urn] = {**fingerprint, "canonical_urn": canonical_urn,
                              "library": library}
        _atomic_write_text(
            fp_path,
            json.dumps(fps, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

        # sources.csv — append/update the row for this relpath.
        src_path = d / "sources.csv"
        _cols, rows = _read_rows(src_path)
        rows = [r for r in rows if r.get("path") != relpath]
        unit_type = ""
        for r in claim_rows:
            if r.get("unit_type"):
                unit_type = r["unit_type"]
                break
        rows.append({
            "source_urn": canonical_urn, "path": relpath, "n_items": len(claim_rows),
            "unit_type": unit_type, "profile": fingerprint.get("profile", ""),
            "provenance": provenance, "library": library, "canonical_urn": canonical_urn,
        })
        rows.sort(key=lambda r: (r.get("path") or ""))
        _write_rows(src_path, SOURCE_COLUMNS, rows)

    def remove_source(self, domain, canonical_urn, relpath) -> None:
        """Drop a source's prior rows (claims by canonical key, fingerprint by key, source by
        relpath) so a changed/removed file replaces its own rows and touches no others."""
        d = self._domain_dir(domain)
        if not d.exists():
            return

        claims_path = d / "claims.csv"
        cols, rows = _read_rows(claims_path)
        if rows or claims_path.exists():
            kept = [r for r in rows if (r.get("canonical_urn") or "") != canonical_urn]
            if kept or rows:
                _write_rows(claims_path, cols or CLAIM_COLUMNS, kept)

        fp_path = d / "fingerprints.json"
        if fp_path.exists():
            # Same loader as append_source: a corrupt store raises here (and is
            # preserved) rather than being silently treated as empty, which would
            # skip the removal and leave a stale fingerprint behind with no signal.
            fps = _load_fingerprint_store(fp_path, domain)
            if canonical_urn in fps:
                fps.pop(canonical_urn, None)
                _atomic_write_text(
                    fp_path,
                    json.dumps(fps, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

        src_path = d / "sources.csv"
        cols, rows = _read_rows(src_path)
        if src_path.exists():
            kept = [r for r in rows if r.get("path") != relpath]
            _write_rows(src_path, cols or SOURCE_COLUMNS, kept)


# ── the sync operations ──────────────────────────────────────────
def _resolve_registry(library_cfg: dict):
    csv_path = library_cfg.get("registry_csv")
    if not csv_path:
        return None
    p = Path(csv_path)
    if not p.exists():
        return None
    return consume.read_registry(p)


def _resolve_identity(reg, match_rel, filename, abspath, profile, namespace):
    """Return ``(canonical_urn, provenance)`` — reuse a registered urn else mint one."""
    if reg is not None:
        reused = reg.reuse_urn(relpath=match_rel, filename=filename)
        if reused:
            return reused, "kg-registry"
    return deterministic_identity(abspath, profile, namespace=namespace)[0], "minted"


def sync_library(library_cfg: dict, state: SyncState, store: KGStore, profile,
                 event_log: EventLog | None = None, force_reextract=False) -> dict:
    """Bring the KG in step with one library: index new+changed files, drop removed ones.

    Mutates ``state`` and the ``store`` in place; the caller saves ``state`` once at the end.
    Returns a per-library report.
    """
    lib_id = library_cfg["id"]
    root = Path(library_cfg["root_path"]).resolve()
    namespace = library_cfg.get("urn_namespace")
    reg_prefix = library_cfg.get("registry_path_prefix") or ""
    reg = _resolve_registry(library_cfg)

    p = plan(library_cfg, root, state, force_changed=force_reextract)
    disk = _walk(root, library_cfg.get("exclude_prefixes", ["_"]))

    report = {"library": lib_id, "new": len(p["new"]), "changed": len(p["changed"]),
              "removed": len(p["removed"]), "indexed": 0, "claims": 0,
              "reuse": 0, "mint": 0, "errors": [], "skipped": []}

    # removed — drop the KG rows, delete the state entry, leave the corpus file alone.
    for rel in p["removed"]:
        entry = state.get(lib_id, rel) or {}
        canonical = entry.get("canonical_urn", "")
        domain = entry.get("domain", "_root")
        if canonical:
            previous_claim_ids = store.claim_ids(domain, canonical)
            if event_log is not None:
                event_log.append("source.removed", "source",
                                 source_object_id(lib_id, rel), {
                    "library": lib_id, "relpath": rel, "domain": domain,
                    "canonical_urn": canonical,
                    "affected_claim_ids": previous_claim_ids,
                })
            store.remove_source(domain, canonical, rel)
        state.remove(lib_id, rel)

    # new + changed — resolve identity, extract, fingerprint, (replace then) append.
    for rel in list(p["new"]) + list(p["changed"]):
        info = disk.get(rel)
        if info is None:  # vanished between plan and now
            report["skipped"].append(rel)
            continue
        abspath = info["abspath"]
        domain = info["domain"]
        filename = abspath.name
        match_rel = (reg_prefix + rel) if reg_prefix else rel

        canonical, provenance = _resolve_identity(
            reg, match_rel, filename, abspath, profile, namespace)

        try:
            res = _extract_file(abspath, canonical, profile)
        except Exception as e:  # a bad/binary file must not sink the pass
            report["errors"].append(
                {"relpath": rel, "error": f"{type(e).__name__}: {e}"})
            continue

        items = res["items"]
        nd_context = None
        if reg is not None:
            prov = reg.provenance_for(relpath=match_rel, filename=filename)
            if prov:
                nd_context = {"jurisdiction": prov.get("jurisdiction", ""),
                              "time": prov.get("detected_year", "")}
        fp_obj = _json_safe(fingerprint(canonical, items, profile, nd_context=nd_context))
        claim_rows = [flatten_claim(it, profile.id) for it in items]
        sha1 = content_sha1(abspath)

        # Persist the source. A corrupt fingerprint store raises inside the store
        # writes (rather than silently wiping itself); record it against this file
        # and keep going, so one damaged domain doesn't sink indexing for every
        # other library. On failure no state/counters are updated, so the source is
        # retried on the next pass.
        try:
            if rel in p["changed"]:
                prev = state.get(lib_id, rel) or {}
                prev_canon = prev.get("canonical_urn") or canonical
                prev_domain = prev.get("domain", domain)
                previous_claim_ids = store.claim_ids(prev_domain, prev_canon)
                if event_log is not None:
                    event_log.append("source.removed", "source",
                                     source_object_id(lib_id, rel), {
                        "library": lib_id, "relpath": rel, "domain": prev_domain,
                        "canonical_urn": prev_canon,
                        "affected_claim_ids": previous_claim_ids,
                    })
                store.remove_source(prev_domain, prev_canon, rel)

            st = abspath.stat()
            state_entry = {
                "sha1": sha1, "canonical_urn": canonical, "size": st.st_size,
                "mtime": int(st.st_mtime), "domain": domain, "n_claims": len(claim_rows)}
            if event_log is not None:
                event_log.append("source.upserted", "source",
                                 source_object_id(lib_id, rel), {
                    "library": lib_id, "relpath": rel, "domain": domain,
                    "canonical_urn": canonical, "provenance": provenance, "sha1": sha1,
                    "claim_rows": claim_rows, "fingerprint": fp_obj,
                    "state_entry": state_entry,
                    "affected_claim_ids": sorted(row.get("item_id", "") for row in claim_rows
                                                 if row.get("item_id")),
                })
            store.append_source(domain, lib_id, canonical, provenance, rel, sha1,
                                claim_rows, fp_obj)
            state.put(lib_id, rel, state_entry)
        except Exception as e:  # corrupt store / disk error: record and keep going
            report["errors"].append({"relpath": rel, "error": f"{type(e).__name__}: {e}"})
            continue

        report["indexed"] += 1
        report["claims"] += len(claim_rows)
        if provenance == "kg-registry":
            report["reuse"] += 1
        else:
            report["mint"] += 1

    return report


def sync_once(config: dict) -> dict:
    """One incremental pass over every library; saves the state once at the end."""
    kg_root = config["kg_root"]
    state = SyncState(kg_root)
    store = KGStore(kg_root)
    event_log = EventLog(kg_root)
    event_log.bootstrap_legacy_projection()
    profile = get_profile(config.get("profile_id", "generic"))

    # K2: the profile is a semantic input to extraction. If the store was last
    # indexed under a different profile (or an unknown one, for legacy states),
    # every known file re-extracts even though its bytes are unchanged.
    signature = {"id": profile.id, "catalogue_version": profile.catalogue_version}
    force = bool(state.files) and state.profile != signature
    if event_log.current_digest("sync:profile") != object_digest({"profile": signature}):
        event_log.append("sync.profile.updated", "sync_profile", "sync:profile",
                         {"profile": signature})
    reports = [sync_library(lib, state, store, profile, event_log,
                            force_reextract=force)
               for lib in config.get("libraries", [])]
    state.profile = signature
    state.save()

    # The nD manifest is a graph_version input — write it before minting.
    nd_registry = config.get("_nd_registry")
    if nd_registry is not None:
        manifest = nd_registry.manifest()
        if event_log.current_digest("nd:manifest") != object_digest({"manifest": manifest}):
            event_log.append("nd.manifest.updated", "nd_manifest", "nd:manifest",
                             {"manifest": manifest})
        (Path(kg_root) / "_nd_systems.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2,
                       sort_keys=True) + "\n", encoding="utf-8")

    version = mint_graph_version(kg_root)
    stamp_graph_version(kg_root, version)

    agg = {"kg_root": str(kg_root), "libraries": reports,
           "graph_version": version}
    for k in ("new", "changed", "removed", "indexed", "claims", "reuse", "mint"):
        agg[k] = sum(r[k] for r in reports)
    agg["errors"] = sum(len(r["errors"]) for r in reports)
    return agg


def seed_state(config: dict) -> dict:
    """Snapshot every current file as 'already indexed' WITHOUT indexing it.

    Records each file's (size, mtime, sha1, canonical_urn, domain) into the state so a
    subsequent :func:`sync_once` / :func:`watch` only picks up files added AFTER seeding —
    the way to declare 'the bulk migration already indexed these'.
    """
    kg_root = config["kg_root"]
    state = SyncState(kg_root)
    event_log = EventLog(kg_root)
    event_log.bootstrap_legacy_projection()
    profile = get_profile(config.get("profile_id", "generic"))

    per_lib = []
    for lib in config.get("libraries", []):
        lib_id = lib["id"]
        root = Path(lib["root_path"]).resolve()
        namespace = lib.get("urn_namespace")
        reg_prefix = lib.get("registry_path_prefix") or ""
        reg = _resolve_registry(lib)
        n = 0
        for rel, info in sorted(_walk(root, lib.get("exclude_prefixes", ["_"])).items()):
            abspath = info["abspath"]
            match_rel = (reg_prefix + rel) if reg_prefix else rel
            canonical, _prov = _resolve_identity(
                reg, match_rel, abspath.name, abspath, profile, namespace)
            st = abspath.stat()
            state_entry = {
                "sha1": content_sha1(abspath), "canonical_urn": canonical,
                "size": st.st_size, "mtime": int(st.st_mtime), "domain": info["domain"],
                "n_claims": 0}
            seed_payload = {
                "library": lib_id, "relpath": rel, "state_entry": state_entry,
                "affected_claim_ids": [],
            }
            object_id = source_object_id(lib_id, rel)
            if event_log.current_digest(object_id) != object_digest(seed_payload):
                event_log.append("source.seeded", "source", object_id, seed_payload)
            state.put(lib_id, rel, state_entry)
            n += 1
        per_lib.append({"library": lib_id, "seeded": n})

    signature = {"id": profile.id, "catalogue_version": profile.catalogue_version}
    if event_log.current_digest("sync:profile") != object_digest({"profile": signature}):
        event_log.append("sync.profile.updated", "sync_profile", "sync:profile",
                         {"profile": signature})
    state.profile = signature
    state.save()
    return {"kg_root": str(kg_root), "libraries": per_lib,
            "total": sum(x["seeded"] for x in per_lib)}


def watch(config: dict) -> int:
    """Poll every ``watch_interval_seconds`` and run :func:`sync_once`. Cross-platform.

    Pure poll loop — no OS filesystem-watch calls. Prints a one-line summary per pass and
    exits cleanly on Ctrl-C.
    """
    interval = config.get("watch_interval_seconds", 30)
    print(f"live-index watching {len(config.get('libraries', []))} librar"
          f"{'y' if len(config.get('libraries', [])) == 1 else 'ies'} "
          f"every {interval}s (Ctrl-C to stop)")
    try:
        while True:
            r = sync_once(config)
            print(f"sync: new={r['new']} changed={r['changed']} removed={r['removed']} "
                  f"indexed={r['indexed']} claims={r['claims']} "
                  f"reuse={r['reuse']} mint={r['mint']} errors={r['errors']}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("live-index stopped")
        return 0
