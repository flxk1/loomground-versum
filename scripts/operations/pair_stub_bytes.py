#!/usr/bin/env python3
"""pair_stub_bytes.py — attach arriving PDF bytes to an EXISTING citation stub's identity.

BACKGROUND. A source often enters the KG as a citation stub first: a `.md` plus a
`.md.metadata.json` sidecar carrying the curated `canonical_urn` and
`pdf_status: "unavailable"`. When the actual PDF turns up later, the default intake
(`versum ingest` → `deterministic_identity`) would mint a NEW URN from the PDF's
title/content-sha — forking the identity the stub already owns.

THE SANCTIONED PROCEDURE (executed manually and verified live on 2026-08-02, see the
two `sidecar-pairing` sidecars in `Library/ai_act_and_regulation/2026/`):

  a. match the arriving PDF to its existing stub — canonical URN, identifier, or
     title lookup against the live corpus (the Library shelf sidecars);
  b. file the PDF into the stub's shelf folder with a paired sidecar carrying the
     STUB's `canonical_urn` (`identity_method: "sidecar-pairing"`,
     `provenance_level: "canonical"`, sha256 of the bytes, `source_url`, and an
     `identity_note` documenting the deliberate pairing);
  c. update the stub's sidecar: `pdf_status` → `"available"`, `pdf_file` → the PDF
     filename.

The next `versum sync` pass then indexes the PDF under the stub URN with provenance
`kg-canonical` (the file's own paired sidecar wins over minting) — zero mints
(verified live: new=2, reuse=2, mint=0). This script never mints and never guesses:
an ambiguous match (more than one stub at the winning tier) is surfaced for a human
to resolve and is refused even under `--apply`.

THIS SCRIPT plans by default (READ-ONLY, prints the pairing plan as JSON) and only
writes with an explicit `--apply`. It copies the PDF (the original stays where it
was), writes the pairing sidecar, and updates the stub sidecar. It never touches the
KG store — indexing is the sync pass's job.

Run:   python3 pair_stub_bytes.py <pdf> [<pdf> ...] --config /path/to/loomground-kg.config.json
       python3 pair_stub_bytes.py <pdf> --urn urn:dls:source:... --source-url https://... --apply
Config resolves from: --config > $LOOMGROUND_KG_CONFIG > ./loomground-kg.config.json >
<this dir>/loomground-kg.config.json.
"""
import sys, os, json, re, shutil, hashlib, argparse
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))

# a paired sidecar's name is "<pdf name>.metadata.json"; both must fit the common
# 255-byte filename limit.
_SIDECAR_SUFFIX = ".metadata.json"
_MAX_NAME_BYTES = 255 - len(_SIDECAR_SUFFIX)


def resolve_config(arg):
    for cand in [arg, os.environ.get("LOOMGROUND_KG_CONFIG"),
                 os.path.join(os.getcwd(), "loomground-kg.config.json"),
                 os.path.join(HERE, "loomground-kg.config.json")]:
        if cand and os.path.exists(cand):
            return cand
    sys.exit("No config found. Pass --config <path> or set LOOMGROUND_KG_CONFIG.")


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", " ", (value or "").lower()).strip()


def _compact(value: str) -> str:
    return _norm(value).replace(" ", "")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_stubs(cfg: dict) -> list:
    """Every citation-stub sidecar (`*.md.metadata.json` with a canonical_urn) across
    the configured libraries — the live lookup the match runs against."""
    stubs = []
    for lib in cfg.get("libraries", []):
        root = Path(lib["root_path"]).resolve()
        if not root.exists():
            continue
        prefixes = tuple(lib.get("exclude_prefixes", ["_"]))
        for sc in sorted(root.rglob("*.md" + _SIDECAR_SUFFIX)):
            parts = sc.relative_to(root).parts
            if any(part.startswith(".") for part in parts):
                continue  # hidden tool state, never corpus (mirrors the sync walk)
            if len(parts) > 1 and parts[0].startswith(prefixes):
                continue
            try:
                d = json.loads(sc.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            urn = (d.get("canonical_urn") or "").strip() if isinstance(d, dict) else ""
            if not urn:
                continue
            stubs.append({
                "library": lib["id"],
                "sidecar_path": sc,
                "stub_name": sc.name[:-len(_SIDECAR_SUFFIX)],
                "shelf": sc.parent,
                "canonical_urn": urn,
                "title": (d.get("title") or "").strip(),
                "identifier": (d.get("identifier") or "").strip(),
                "year": str(d.get("year") or "").strip(),
                "pdf_status": (d.get("pdf_status") or "").strip(),
                "pdf_file": (d.get("pdf_file") or "").strip(),
                "download_url": (d.get("download_url") or "").strip(),
                "landing_url": (d.get("landing_url") or "").strip(),
            })
    return stubs


def match_stub(pdf_name: str, stubs: list, urn: str | None = None):
    """Return ``(matches, method)`` — ALL stubs matching at the winning tier.

    Tiers: explicit ``--urn``; then a stub's curated identifier appearing in the PDF
    filename (compact comparison, so "BT-Drs. 21/6407" matches "bt-drs 21-6407");
    then title-word overlap (same threshold as ``versum.store.kg.provenance_urn_for``).
    More than one match at the winning tier means AMBIGUOUS — the caller must not
    pick one.
    """
    if urn:
        return [s for s in stubs if s["canonical_urn"] == urn.strip()], "urn"
    stem = Path(pdf_name).stem
    name_c = _compact(stem)
    hits = [s for s in stubs
            if len(_compact(s["identifier"])) >= 6 and _compact(s["identifier"]) in name_c]
    if hits:
        return hits, "identifier"
    name_n = _norm(stem)
    hits = []
    for s in stubs:
        words = [w for w in _norm(s["title"]).split() if len(w) > 4]
        if words and sum(w in name_n for w in words) >= max(2, len(words) // 3):
            hits.append(s)
    return hits, "title"


def _pairing_sidecar(stub: dict, pdf_name: str, sha: str, source_url: str,
                     verification: str, method: str, today: str) -> dict:
    # field shape copied from the two live sidecar-pairing sidecars of 2026-08-02
    return {
        "canonical_urn": stub["canonical_urn"],
        "identifier": stub["identifier"],
        "identity_method": "sidecar-pairing",
        "provenance_level": "canonical",
        "title": stub["title"],
        "verification": verification or
            f"paired {today} via pair_stub_bytes.py (matched to existing stub by {method}; "
            f"sha256 of the received bytes recorded)",
        "sha256": sha,
        "source_file": pdf_name,
        "source_url": source_url or stub["download_url"] or stub["landing_url"],
        "year": stub["year"],
        "identity_note": f"Deliberate pairing {today} via pair_stub_bytes.py: bytes "
                         f"attached to the existing citation stub's canonical URN "
                         f"(stub: {stub['stub_name']}); no new identity minted.",
    }


def _stub_view(stub: dict) -> dict:
    return {"library": stub["library"], "stub": stub["stub_name"],
            "canonical_urn": stub["canonical_urn"], "shelf": str(stub["shelf"]),
            "identifier": stub["identifier"], "title": stub["title"]}


def plan_pairs(cfg: dict, pdf_paths: list, urn: str | None = None,
               source_url: str = "", verification: str = "") -> dict:
    """READ-ONLY: match every arriving PDF to a stub and describe the exact writes."""
    stubs = load_stubs(cfg)
    today = datetime.now(timezone.utc).date().isoformat()
    pairs = []
    for raw in pdf_paths:
        pdf = Path(raw)
        entry = {"pdf": str(pdf)}
        pairs.append(entry)
        if not pdf.is_file():
            entry.update(status="missing-pdf",
                         detail="file does not exist or is not a regular file")
            continue
        if len(pdf.name.encode("utf-8")) > _MAX_NAME_BYTES:
            entry.update(status="name-too-long",
                         detail=f"filename must stay within {_MAX_NAME_BYTES} bytes so its "
                                f"'{_SIDECAR_SUFFIX}' sidecar name fits the 255-byte limit; "
                                f"rename the file first")
            continue
        matches, method = match_stub(pdf.name, stubs, urn=urn)
        if not matches:
            entry.update(status="no-match",
                         detail="no stub matched by URN, identifier, or title; if this is a "
                                "genuinely new source, use the normal intake instead")
            continue
        if len(matches) > 1:
            entry.update(status="ambiguous", match_method=method,
                         candidates=[_stub_view(s) for s in matches],
                         detail="more than one stub matched — resolve by re-running with "
                                "--urn <the correct canonical_urn>")
            continue
        stub = matches[0]
        dest = stub["shelf"] / pdf.name
        sha = _sha256(pdf)
        entry.update(match_method=method, stub=_stub_view(stub))
        if stub["pdf_status"] == "available":
            if stub["pdf_file"] == pdf.name and dest.exists() and _sha256(dest) == sha:
                entry.update(status="already-filed",
                             detail="stub already carries exactly these bytes; nothing to do")
            else:
                entry.update(status="already-paired",
                             detail=f"stub already has pdf_status 'available' "
                                    f"(pdf_file: {stub['pdf_file'] or '?'}); refusing to "
                                    f"pair a second file onto the same identity")
            continue
        if dest.exists():
            entry.update(status="dest-exists",
                         detail=f"{dest} already exists with different provenance; "
                                f"resolve by hand")
            continue
        entry.update(status="pair", sha256=sha, writes={
            "file_pdf": str(dest),
            "write_sidecar": str(dest) + _SIDECAR_SUFFIX,
            "update_stub_sidecar": str(stub["sidecar_path"]),
        }, _stub=stub, _pdf=pdf,
            _sidecar=_pairing_sidecar(stub, pdf.name, sha, source_url,
                                      verification, method, today))
    return {"n_stubs_scanned": len(stubs), "pairs": pairs,
            "clean": all(p["status"] in ("pair", "already-filed") for p in pairs)}


def apply_pairs(plan: dict) -> None:
    """Perform the planned writes in place (mutates the plan entries' status)."""
    for entry in plan["pairs"]:
        if entry.get("status") != "pair":
            continue
        stub, pdf = entry.pop("_stub"), entry.pop("_pdf")
        sidecar = entry.pop("_sidecar")
        dest = Path(entry["writes"]["file_pdf"])
        shutil.copy2(pdf, dest)
        Path(entry["writes"]["write_sidecar"]).write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        d = json.loads(stub["sidecar_path"].read_text(encoding="utf-8"))
        d["pdf_status"] = "available"
        d["pdf_file"] = pdf.name
        stub["sidecar_path"].write_text(
            json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        entry["status"] = "paired"


def _printable(plan: dict) -> dict:
    out = dict(plan)
    out["pairs"] = [{k: v for k, v in e.items() if not k.startswith("_")}
                    for e in plan["pairs"]]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdfs", nargs="+", help="arriving PDF file(s) to pair")
    ap.add_argument("--config", default=None)
    ap.add_argument("--urn", default=None,
                    help="pair with exactly this stub canonical_urn (single PDF only); "
                         "use it to resolve an ambiguous match")
    ap.add_argument("--source-url", default="",
                    help="where the bytes came from (single PDF only); defaults to the "
                         "stub sidecar's download_url / landing_url")
    ap.add_argument("--verification", default="",
                    help="verification note for the pairing sidecar (single PDF only)")
    ap.add_argument("--apply", action="store_true",
                    help="perform the pairing writes; default is a read-only plan")
    args = ap.parse_args()
    if len(args.pdfs) > 1 and (args.urn or args.source_url or args.verification):
        ap.error("--urn / --source-url / --verification apply to a single PDF only")

    cfg_path = resolve_config(args.config)
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))

    plan = plan_pairs(cfg, args.pdfs, urn=args.urn, source_url=args.source_url,
                      verification=args.verification)
    if not args.apply:
        print(json.dumps(_printable(plan), ensure_ascii=False, indent=2))
        print("\nDRY RUN — nothing written. Pair with: --apply", file=sys.stderr)
        return 0 if plan["clean"] else 1

    apply_pairs(plan)
    print(json.dumps(_printable(plan), ensure_ascii=False, indent=2))
    if any(e["status"] == "paired" for e in plan["pairs"]):
        print(f"\nPaired. Index with: python -m versum sync --config {cfg_path}",
              file=sys.stderr)
    return 0 if plan["clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
