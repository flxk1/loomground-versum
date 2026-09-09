#!/usr/bin/env python3
"""dedupe_audit.py — report (and optionally quarantine) duplicate-identity sources.

One canonical URN mapping to several library files means the same document is
indexed more than once — every extra copy double-counts its claims in the store.
This audit reads the Live Index state per library and groups source entries by
``canonical_urn``: every URN with more than one relpath is a *duplicate family*.

READ-ONLY by default: prints the full report as JSON. With ``--apply`` and
``--quarantine-dir`` it MOVES each family's non-keeper members out of the library
(never deletes), preserving relative paths under ``<quarantine>/<library_id>/``,
so the next ``versum sync`` drops exactly their rows through the sanctioned
removal path. Keeper policy: the shortest relpath, ties broken lexicographically
— copy suffixes ("__2", " (1)") lengthen names, so the base copy wins
deterministically.

Safety rails (learned from a live 2026-08 cleanup):
  * a member with a paired capture sidecar is a curated identity — reported but
    skipped unless ``--include-curated``; a moved member takes its sidecar along;
  * a family with any member missing on disk is *stale* (state ahead of disk):
    nothing in it moves — run ``versum sync`` first;
  * the quarantine dir must not sit inside a library root unless its first path
    component starts with that library's exclude prefix (else the Live Index
    walk would re-index the quarantined copies as corpus);
  * name comparisons normalize unicode to NFC — macOS lists NFD, and a byte-wise
    comparison of the two spellings silently mismatches.

Run:   python3 dedupe_audit.py --config /path/to/config.json
       python3 dedupe_audit.py --config ... --apply --quarantine-dir /path/outside
Config resolves from: --config > $LOOMGROUND_KG_CONFIG > ./loomground-kg.config.json >
<this dir>/loomground-kg.config.json. Engine: $VERSUM_ENGINE > repository checkout.
"""
import argparse
import json
import os
import shutil
import sys
import unicodedata
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.environ.get("VERSUM_ENGINE", str(Path(HERE).parents[1]))
sys.path.insert(0, os.path.join(ENGINE, "src"))


def resolve_config(arg):
    for cand in [arg, os.environ.get("LOOMGROUND_KG_CONFIG"),
                 os.path.join(os.getcwd(), "loomground-kg.config.json"),
                 os.path.join(HERE, "loomground-kg.config.json")]:
        if cand and os.path.exists(cand):
            return cand
    sys.exit("No config found. Pass --config <path> or set LOOMGROUND_KG_CONFIG.")


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def audit(cfg: dict, include_curated: bool = False) -> dict:
    """READ-ONLY: group each library's state entries by canonical URN and plan moves."""
    from versum.sync import SyncState

    state = SyncState(cfg["kg_root"])
    report = {"kg_root": str(cfg["kg_root"]), "libraries": []}
    for lib in cfg.get("libraries", []):
        lib_id = lib["id"]
        root = Path(lib["root_path"])
        prefix = lib_id + "::"
        by_urn: dict = {}
        for key, entry in state.files.items():
            if not key.startswith(prefix):
                continue
            by_urn.setdefault(entry.get("canonical_urn", ""), []).append(
                {"relpath": key[len(prefix):], **entry})
        families, moves, skipped_curated, stale_count = [], [], 0, 0
        for urn, members in sorted(by_urn.items()):
            if len(members) < 2:
                continue
            members.sort(key=lambda m: (len(_nfc(m["relpath"])), _nfc(m["relpath"])))
            keeper = members[0]
            stale = any(not (root / m["relpath"]).is_file() for m in members)
            fam = {"canonical_urn": urn, "keeper": keeper["relpath"],
                   "stale": stale, "members": []}
            for m in members[1:]:
                curated = (root / (m["relpath"] + ".metadata.json")).is_file()
                fam["members"].append({
                    "relpath": m["relpath"],
                    "n_claims": m.get("n_claims", 0),
                    "byte_identical_to_keeper": m.get("sha1") == keeper.get("sha1"),
                    "curated": curated,
                })
                if stale:
                    continue
                if curated and not include_curated:
                    skipped_curated += 1
                    continue
                moves.append({"relpath": m["relpath"], "curated": curated})
            stale_count += stale
            families.append(fam)
        report["libraries"].append({
            "id": lib_id, "root": str(root),
            "duplicate_families": len(families),
            "duplicate_members": sum(len(f["members"]) for f in families),
            "claims_double_counted": sum(m["n_claims"] for f in families
                                         for m in f["members"]),
            "moves_planned": [m["relpath"] for m in moves],
            "skipped_curated": skipped_curated,
            "stale_families": stale_count,
            "families": families,
            "_moves": moves,
        })
    return report


def guard_quarantine(root: Path, quarantine: Path, exclude_prefixes) -> None:
    """Refuse a quarantine dir the Live Index walk would re-index as corpus."""
    q, r = quarantine.resolve(), root.resolve()
    if r not in q.parents:
        return
    top = q.relative_to(r).parts[0]
    if any(top.startswith(pfx) for pfx in tuple(exclude_prefixes or ())):
        return
    sys.exit(f"quarantine dir {q} is inside library root {r} and not covered by an "
             f"exclude prefix — the Live Index walk would re-index it")


def apply_moves(cfg: dict, report: dict, quarantine: Path) -> int:
    """Move every planned non-keeper (and its sidecar) into the quarantine dir."""
    moved = 0
    for lib, lib_report in zip(cfg.get("libraries", []), report["libraries"]):
        root = Path(lib["root_path"])
        guard_quarantine(root, quarantine, lib.get("exclude_prefixes", ["_"]))
        for move in lib_report["_moves"]:
            src = root / move["relpath"]
            target = quarantine / lib_report["id"] / move["relpath"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(target))
            sidecar = root / (move["relpath"] + ".metadata.json")
            if sidecar.is_file():
                shutil.move(str(sidecar), str(target) + ".metadata.json")
            moved += 1
    return moved


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=None)
    ap.add_argument("--apply", action="store_true",
                    help="move planned members into --quarantine-dir (default: report only)")
    ap.add_argument("--quarantine-dir", default=None)
    ap.add_argument("--include-curated", action="store_true",
                    help="also plan moves for sidecar-paired (curated) members")
    args = ap.parse_args()

    from versum.sync import load_config
    cfg = load_config(resolve_config(args.config))
    report = audit(cfg, include_curated=args.include_curated)

    if args.apply:
        if not args.quarantine_dir:
            sys.exit("--apply requires --quarantine-dir")
        moved = apply_moves(cfg, report, Path(args.quarantine_dir))
        report["moved"] = moved
        report["next"] = "run `python -m versum sync --config ...` to drop the moved rows"
    for lib_report in report["libraries"]:
        lib_report.pop("_moves", None)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
