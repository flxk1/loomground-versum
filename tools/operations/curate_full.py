#!/usr/bin/env python3
"""curate_full.py — coordinate-identity curation over a whole materialized KG.

Turns the 392k already-extracted claims into the mental-model / concept layer: every claim
gets a content-derived 5D+nD coordinate; claims that share a coordinate (across sources and
across domains) name the SAME concept, so the concept layer emerges by convergence. Fills
the currently-empty ``concepts.csv`` + ``semantic_edges.csv`` in each ``by-domain/<domain>/``
and writes a global ``canon.json`` (the domain canon) + ``convergence.json`` (the mint curve)
at the KG root.

This is CPU-light: it reads claim rows already on disk — no PDF parsing, no network, no
model. It is safe to run as a long Terminal session and is RESUMABLE and PARALLEL: each
domain is an independent job; a finished domain is skipped on re-run unless its
``claims.csv`` changed. Nothing is deleted or overwritten except the two concept tables
(previously empty) and the canon/convergence reports.

Device-neutral: every machine path comes from the config file, never from this script.

    Config resolution (first that exists wins):
      --config <path>  >  $LOOMGROUND_KG_CONFIG  >  ./loomground-kg.config.json
    Engine resolution:
      $VERSUM_ENGINE  >  ./loomground-versum  (a checkout of the versum engine)

    Usage:
      python3 curate_full.py --config /path/to/loomground-kg.config.json
      python3 curate_full.py --config ... --workers 4 --m-max 1
      python3 curate_full.py --config ... --force        # recurate every domain
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent


# ── engine + config resolution (device-neutral) ───────────────────────────────
def resolve_engine() -> Path:
    cand = os.environ.get("VERSUM_ENGINE") or str(HERE.parents[1])
    p = Path(cand).expanduser().resolve()
    if not (p / "src" / "versum" / "canon.py").is_file():
        sys.exit(f"[curate] engine not found at {p} — set $VERSUM_ENGINE to a versum checkout")
    return p


def resolve_config(arg: str | None) -> Path:
    for cand in (arg, os.environ.get("LOOMGROUND_KG_CONFIG"),
                 str(HERE / "loomground-kg.config.json"),
                 "./loomground-kg.config.json"):
        if cand and Path(cand).expanduser().is_file():
            return Path(cand).expanduser().resolve()
    sys.exit("[curate] no config: pass --config, set $LOOMGROUND_KG_CONFIG, "
             "or place loomground-kg.config.json next to this script")


# ── per-domain job (runs in a worker process) ─────────────────────────────────
def _curate_one(job: dict) -> dict:
    sys.path.insert(0, str(Path(job["engine"]) / "src"))
    from versum.concept.canon import curate_domain_folder
    t0 = time.time()
    try:
        r = curate_domain_folder(job["folder"], domain=job["domain"],
                                 m_max=job["m_max"], catalogue_version=job["catalogue_version"],
                                 morph_language=job.get("morph_language"))
        r["ok"] = True
    except Exception as e:  # a bad domain must not sink the run
        r = {"domain": job["domain"], "ok": False, "error": f"{type(e).__name__}: {e}"}
    r["seconds"] = round(time.time() - t0, 1)
    return r


def _claims_sig(folder: Path) -> str:
    st = (folder / "claims.csv").stat()
    return f"{st.st_size}:{int(st.st_mtime)}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Coordinate-identity curation over a KG.")
    ap.add_argument("--config", default=None)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--m-max", type=int, default=1)
    ap.add_argument("--force", action="store_true", help="recurate every domain")
    args = ap.parse_args(argv)

    engine = resolve_engine()
    sys.path.insert(0, str(engine / "src"))
    from versum.sync import load_config

    cfg_path = resolve_config(args.config)
    cfg = load_config(cfg_path)
    kg_root = Path(cfg["kg_root"]).expanduser().resolve()
    by_domain = kg_root / "by-domain"
    root = by_domain if by_domain.is_dir() else kg_root
    catalogue_version = str(cfg.get("catalogue_version", "") or "")
    morph_language = cfg.get("morph_language")

    state_dir = kg_root / "_curate"
    state_dir.mkdir(parents=True, exist_ok=True)
    done_file = state_dir / "_done_domains.json"       # {domain: claims_sig}
    done = {} if args.force else (
        json.loads(done_file.read_text()) if done_file.exists() else {})

    domains = sorted(p for p in root.iterdir()
                     if p.is_dir() and not p.name.startswith("_")
                     and (p / "claims.csv").exists())
    jobs, skipped = [], 0
    for d in domains:
        sig = _claims_sig(d)
        if done.get(d.name) == sig and (d / "canon.partial.json").exists():
            skipped += 1
            continue
        jobs.append({"engine": str(engine), "folder": str(d), "domain": d.name,
                     "m_max": args.m_max, "catalogue_version": catalogue_version,
                     "morph_language": morph_language,
                     "_sig": sig})

    print(f"[curate] kg_root={kg_root}")
    print(f"[curate] {len(domains)} domains | {len(jobs)} to curate | {skipped} up-to-date "
          f"| workers={args.workers} m_max={args.m_max}", flush=True)

    t0 = time.time()
    results, errors = [], []
    if jobs:
        with Pool(processes=min(args.workers, len(jobs))) as pool:
            for i, r in enumerate(pool.imap_unordered(_curate_one, jobs), 1):
                results.append(r)
                if r.get("ok"):
                    done[r["domain"]] = next(j["_sig"] for j in jobs
                                             if j["domain"] == r["domain"])
                    done_file.write_text(json.dumps(done, indent=2))
                    print(f"[curate] ({i}/{len(jobs)}) {r['domain']}: "
                          f"{r['n_concepts']} concepts / {r['n_sources']} sources / "
                          f"{r['n_claims']} claims  [{r['seconds']}s]", flush=True)
                else:
                    errors.append(r)
                    print(f"[curate] ({i}/{len(jobs)}) {r['domain']}: ERROR {r['error']}",
                          flush=True)

    # ── reduce: merge every domain partial into the global canon ───────────────
    print("[curate] merging partials -> canon.json + convergence.json ...", flush=True)
    from versum.concept.canon import merge_partials, IDENTITY_AXES
    partials = []
    for d in domains:
        pj = d / "canon.partial.json"
        if pj.exists():
            try:
                partials.append(json.loads(pj.read_text(encoding="utf-8")))
            except Exception as e:
                errors.append({"domain": d.name, "error": f"partial unreadable: {e}"})
    merged = merge_partials(partials)
    (kg_root / "canon.json").write_text(json.dumps(
        {"m_max": args.m_max, "identity_axes": list(IDENTITY_AXES),
         "n_domains": len(partials),
         **{k: merged[k] for k in ("n_concepts", "n_claims", "n_unclustered",
                                   "clustered_rate", "n_sources",
                                   "canon_by_domain", "concepts")}},
        ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (kg_root / "convergence.json").write_text(json.dumps(
        {"m_max": args.m_max, "curve": merged["convergence"]},
        ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    # ── human-readable summary (so quality is visible immediately) ─────────────
    mins = round((time.time() - t0) / 60, 1)
    print("\n" + "=" * 68)
    print(f"[curate] DONE in {mins} min | {merged['n_concepts']} concepts "
          f"from {merged['n_claims']} claims across {merged['n_sources']} sources "
          f"/ {len(partials)} domains")
    print(f"[curate] clustered {merged['clustered_rate']*100:.1f}% of claims into concepts; "
          f"{merged['n_unclustered']} claims had no corpus-salient subject (residue)")
    if errors:
        print(f"[curate] {len(errors)} domain error(s): "
              + ", ".join(e['domain'] for e in errors))
    top = merged["concepts"][:15]
    print("\nTop concepts by cross-source support (n_sources / n_claims):")
    for c in top:
        doms = ",".join(c["domains"][:3]) + ("…" if len(c["domains"]) > 3 else "")
        print(f"  {c['n_sources']:>4}s {c['n_claims']:>6}c  {c['concept_id']:<40} [{doms}]")
    cur = merged["convergence"]
    if cur:
        tail = cur[-1]
        print(f"\nConvergence: {tail['n_distinct']} distinct coordinates after "
              f"{len(cur)} sources; last source minted {tail['n_new']} new.")
    cbd = merged["canon_by_domain"]
    print(f"\nCanon size by domain (top 8 of {len(cbd)}):")
    for dom, n in sorted(cbd.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {n:>5}  {dom}")
    print(f"\nWrote: {kg_root/'canon.json'}")
    print(f"       {kg_root/'convergence.json'}")
    print(f"       by-domain/*/concepts.csv + semantic_edges.csv")
    print("=" * 68)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
