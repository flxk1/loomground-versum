"""organise.py — the mechanical half of the organise-Versum skill.

Surfaces placement EVIDENCE for the LLM; it never files anything and never decides a domain.
Two things it does:

  list     — show what is waiting in the review queue (from each item's provenance sidecar).
  suggest  — rank the domains + nearest sources for a document's concept set (via inbox.suggest),
             so the model can propose a placement a person confirms.

A document's concept set comes from the engine extractor (run capture/sync first); this script
only reads and ranks. No network. No write — writing is the loomground-knowledge-write path.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# self-contained: the ranking module is bundled beside this script; the sidecar suffix is the
# one product-layer constant this helper needs, inlined so the plugin has no engine import.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import suggest as S

SIDE = ".metadata.json"


def cmd_list(args):
    review = Path(args.review)
    if not review.is_dir():
        raise ValueError(f"review directory not found: {review}")
    items = []
    for sc in sorted(review.glob("*" + SIDE)):
        try:
            d = json.loads(sc.read_text(encoding="utf-8"))
        except Exception:
            continue
        items.append({"artifact": sc.name[:-len(SIDE)], "urn": d.get("canonical_urn", ""),
                      "year": d.get("year", ""), "provenance_level": d.get("provenance_level", "")})
    print(json.dumps({"review_queue": items, "n": len(items)}, ensure_ascii=False, indent=2))


def _concepts_for_urn(store, urn):
    import glob, os
    out = set()
    for f in glob.glob(os.path.join(store, "by-domain", "*", "concepts.csv")):
        with open(f, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("canonical_urn") == urn and row.get("concept_id"):
                    out.add(row["concept_id"])
    return out


def cmd_suggest(args):
    store = Path(args.store)
    if not (store / "by-domain").is_dir():
        raise ValueError(f"concept store not found: {store / 'by-domain'}")
    if args.top_k < 1:
        raise ValueError("--top-k must be at least 1")
    idx = S.build_index(args.store)
    policy = S.load_policy(args.config)         # effort policy from the workspace config (or default)
    if args.concepts:
        concepts = [c.strip() for c in args.concepts.split(",") if c.strip()]
        exclude = None
    elif args.urn:
        concepts = _concepts_for_urn(args.store, args.urn)
        exclude = args.urn                      # leave-one-out when re-ranking an indexed source
    else:
        print("provide --concepts or --urn", file=sys.stderr); sys.exit(2)
    out = S.suggest(concepts, idx, top_k=args.top_k, exclude_urn=exclude, policy=policy)
    out["effort_mode"] = policy.mode
    out["note"] = ("suggestion only — a person confirms the domain/year before any write; "
                   "no shared concept above the queue means route to _review, do not guess")
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_config(args):
    """Show the effort policy in a config file, or write a default one to init it."""
    p = Path(args.path)
    if args.init:
        if p.exists() and not args.force:
            print(f"{p} exists; pass --force to overwrite", file=sys.stderr); sys.exit(2)
        p.parent.mkdir(parents=True, exist_ok=True)
        default = {"effort": {"mode": "cascade", "allow_cloud": False,
                              "local_available": True, "dominance": 0.5, "min_signal": 0.02}}
        p.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote default effort policy to {p}")
    pol = S.load_policy(str(p))
    print(json.dumps({"mode": pol.mode, "allow_cloud": pol.allow_cloud,
                      "local_available": pol.local_available,
                      "dominance": pol.dominance, "min_signal": pol.min_signal},
                     ensure_ascii=False, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(description="Organise-Versum evidence helper (no writes).")
    sub = p.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("list", help="show the review queue")
    pl.add_argument("--review", required=True)
    pl.set_defaults(fn=cmd_list)
    ps = sub.add_parser("suggest", help="rank domains + nearest sources for a concept set")
    ps.add_argument("--store", required=True, help="kg_root (holds by-domain/)")
    ps.add_argument("--concepts", help="comma-separated concept_ids from the engine extractor")
    ps.add_argument("--urn", help="rank an already-indexed source by its stored concepts")
    ps.add_argument("--config", help="effort policy JSON (workspace config); default cascade if absent")
    ps.add_argument("--top-k", type=int, default=5)
    ps.set_defaults(fn=cmd_suggest)
    pc = sub.add_parser("config", help="show or init the effort policy")
    pc.add_argument("path", help="path to the effort-policy JSON in the workspace")
    pc.add_argument("--init", action="store_true", help="write a default policy file")
    pc.add_argument("--force", action="store_true", help="overwrite an existing file on --init")
    pc.set_defaults(fn=cmd_config)
    args = p.parse_args(argv)
    try:
        args.fn(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
