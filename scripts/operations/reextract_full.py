#!/usr/bin/env python3
"""reextract_full.py — re-extract the whole KG with the fixed PDF spacing (ADR-002).

Same operation as the original migration, re-run with the space-inference extractor so claim
text no longer carries "lost spaces" (merged words). Config-driven and device/OS/domain-
neutral: ALL machine paths live in the config file, never in this code. Parallel per-domain,
resumable, READ-ONLY on the corpus. Reuses each library registry's canonical_urn and writes
the canonical-keyed 5D+nD index to <kg_root>/by-domain/<domain>/.

IMPORTANT ordering: this REGENERATES each domain's claims.csv and RESETS its concepts.csv /
semantic_edges.csv to empty (curation output). So the sequence is:
    1) reextract_full.py   (regenerate claims with fixed spacing; concepts reset)
    2) curate_full.py      (rebuild the coordinate-identity canon on the clean claims)

Run:   python3 reextract_full.py --config /path/to/loomground-kg.config.json --force
Config resolves from: --config > $LOOMGROUND_KG_CONFIG > ./loomground-kg.config.json >
<this dir>/loomground-kg.config.json. Engine: $VERSUM_ENGINE > repository checkout.
"""
import sys, os, json, time, csv, shutil, argparse
from pathlib import Path
from multiprocessing import Pool, cpu_count

HERE = os.path.dirname(os.path.abspath(__file__))


def resolve_config(arg):
    for cand in [arg, os.environ.get("LOOMGROUND_KG_CONFIG"),
                 os.path.join(os.getcwd(), "loomground-kg.config.json"),
                 os.path.join(HERE, "loomground-kg.config.json")]:
        if cand and os.path.exists(cand):
            return json.load(open(cand, encoding="utf-8")), cand
    sys.exit("No config found. Pass --config <path> or set LOOMGROUND_KG_CONFIG.")


ENGINE = os.environ.get("VERSUM_ENGINE", str(Path(HERE).parents[1]))
sys.path.insert(0, os.path.join(ENGINE, "src"))

_reg = _cfg = None


def _init(cfg, regcsv):
    global _reg, _cfg
    from versum.io import consume
    import versum.profiles  # noqa: F401  (register built-in profiles)
    _cfg = cfg
    _reg = consume.read_registry(regcsv) if regcsv else None


def _resolve_profile(cfg, library, dom, default_profile):
    """Per-domain profile: config ``domain_profiles`` (a ``domain -> profile_id`` map, exact
    then a ``library:domain`` key) overrides the library / global default. Lets non-law
    domains be extracted with a non-legal profile so their 5D axes are not mis-stamped."""
    dp = cfg.get("domain_profiles") or {}
    return (dp.get(f"{library}:{dom}") or dp.get(dom) or default_profile)


def _do_domain(task):
    lib_id, lib_root, ns, dom, kg_root, scratch, profile_id = task
    from versum.store.index import index_folder
    from versum import materialize
    t = time.time(); outv = os.path.join(scratch, dom, ".versum")
    try:
        m = index_folder(os.path.join(lib_root, dom), profile_id=profile_id, out=outv,
                         consume=_reg, library=lib_id, namespace=ns, use_kg_provenance=False)
        materialize.materialize(os.path.join(scratch, dom),
                                os.path.join(kg_root, "by-domain", dom), library=lib_id)
        srcs = list(csv.DictReader(open(os.path.join(outv, "sources.csv"), encoding="utf-8")))
        shutil.rmtree(os.path.join(scratch, dom), ignore_errors=True)
        return {"dom": dom, "profile": profile_id, "sources": m["n_sources"],
                "claims": m["n_claims"],
                "reuse": sum(1 for s in srcs if s["provenance"] == "kg-registry"),
                "mint": sum(1 for s in srcs if s["provenance"] == "minted"),
                "secs": round(time.time() - t, 1)}
    except Exception as e:
        shutil.rmtree(os.path.join(scratch, dom), ignore_errors=True)
        return {"dom": dom, "error": f"{type(e).__name__}: {e}", "secs": round(time.time() - t, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--force", action="store_true",
                    help="re-extract every domain, ignoring resume markers (use for the fix)")
    ap.add_argument("--workers", type=int, default=max(1, cpu_count() - 1))
    args = ap.parse_args()
    cfg, cfgpath = resolve_config(args.config)
    print(f"[reextract] config: {cfgpath}", flush=True)
    print(f"[reextract] engine: {ENGINE}", flush=True)
    kg_root = cfg["kg_root"]; profile_id = cfg.get("profile_id", "generic")
    exclude = tuple(cfg.get("exclude_prefixes", ["_"]))
    scratch = os.path.join(HERE, "scratch")
    os.makedirs(os.path.join(kg_root, "by-domain"), exist_ok=True)
    os.makedirs(scratch, exist_ok=True)
    libjson = {L["id"]: {"root_path": L["root_path"], "urn_namespace": L["urn_namespace"],
                         "registry_path_prefix": L.get("registry_path_prefix", "")}
               for L in cfg["libraries"]}
    json.dump(libjson, open(os.path.join(kg_root, "libraries.json"), "w"), indent=2)
    done_f = os.path.join(kg_root, "_reextract_done.txt")
    done = set() if args.force else (
        set(open(done_f).read().split()) if os.path.exists(done_f) else set())
    for L in cfg["libraries"]:
        root = L["root_path"]
        if not os.path.isdir(root):
            print(f"[reextract] SKIP library {L['id']}: root not found {root}", flush=True)
            continue
        lib_profile = L.get("profile_id", profile_id)
        domains = sorted(d for d in os.listdir(root)
                         if os.path.isdir(os.path.join(root, d)) and not d.startswith(exclude)
                         and f"{L['id']}/{d}" not in done)
        tasks = [(L["id"], root, L["urn_namespace"], d, kg_root, scratch,
                  _resolve_profile(cfg, L["id"], d, lib_profile)) for d in domains]
        n_nondefault = sum(1 for t in tasks if t[6] != lib_profile)
        tot = {"library": L["id"], "domains": len(domains), "sources": 0, "claims": 0,
               "reuse": 0, "mint": 0, "errors": 0}
        print(f"[reextract] library {L['id']}: {len(domains)} domains; workers={args.workers}; "
              f"default profile={lib_profile}"
              + (f"; {n_nondefault} domain(s) use a per-domain profile" if n_nondefault else ""),
              flush=True)
        t0 = time.time()
        with Pool(processes=min(args.workers, max(1, len(tasks))), initializer=_init,
                  initargs=(cfg, L.get("registry_csv"))) as pool:
            for r in pool.imap_unordered(_do_domain, tasks):
                if "error" in r:
                    tot["errors"] += 1
                    open(os.path.join(kg_root, "_reextract_errors.log"), "a").write(
                        f"{L['id']}/{r['dom']}: {r['error']}\n")
                    print(f"[reextract] ERROR {r['dom']}: {r['error']}", flush=True)
                else:
                    for k in ("sources", "claims", "reuse", "mint"):
                        tot[k] += r[k]
                    print(f"[reextract] {r['dom']} [{r.get('profile','')}]: {r['sources']} src, "
                          f"{r['claims']} claims, reuse={r['reuse']} mint={r['mint']} "
                          f"({r['secs']}s)", flush=True)
                done.add(f"{L['id']}/{r['dom']}")
                open(done_f, "w").write("\n".join(sorted(done)))
                tot["elapsed_min"] = round((time.time() - t0) / 60, 1)
                json.dump({**tot, "status": "RUNNING"},
                          open(os.path.join(kg_root, "_reextract_progress.json"), "w"), indent=2)
        json.dump({**tot, "status": "COMPLETE"},
                  open(os.path.join(kg_root, "_reextract_progress.json"), "w"), indent=2)
        print(f"[reextract] {L['id']} COMPLETE: {tot['sources']} sources, {tot['claims']} "
              f"claims, reuse={tot['reuse']} mint={tot['mint']} errors={tot['errors']} in "
              f"{tot['elapsed_min']} min", flush=True)
    print("[reextract] DONE. Next: run curate_full.py to rebuild the canon on clean claims.",
          flush=True)


if __name__ == "__main__":
    main()
