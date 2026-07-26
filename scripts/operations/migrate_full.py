#!/usr/bin/env python3
"""migrate_full.py — one-shot bulk build of the Loomground Versum KG from a library.

Config-driven and device/OS/domain-neutral: ALL machine-specific paths live in a config
file (see config.example.json), never in this code. Parallel per-domain, resumable, READ-ONLY
on the corpus. Reuses the KG canonical_urn from each library's registry; writes the
canonical-keyed 5D+nD index to <kg_root>/by-domain/<domain>/.

Run:   python3 migrate_full.py --config /path/to/loomground-kg.config.json
Config resolves from: --config > $LOOMGROUND_KG_CONFIG > ./loomground-kg.config.json >
<this dir>/loomground-kg.config.json.
"""
import sys, os, json, time, csv, shutil, argparse
from pathlib import Path
from multiprocessing import Pool, cpu_count

def resolve_config(arg):
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in [arg, os.environ.get("LOOMGROUND_KG_CONFIG"),
                 os.path.join(os.getcwd(), "loomground-kg.config.json"),
                 os.path.join(here, "loomground-kg.config.json")]:
        if cand and os.path.exists(cand):
            return json.load(open(cand, encoding="utf-8")), cand
    sys.exit("No config found. Pass --config <path> or set LOOMGROUND_KG_CONFIG "
             "(see config.example.json).")

# default to this repository checkout; overridable via $VERSUM_ENGINE
ENGINE = os.environ.get("VERSUM_ENGINE",
                        str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, os.path.join(ENGINE, "src"))

_reg = _prof = _cfg = None
def _init(cfg, regcsv, profile_id):
    global _reg, _prof, _cfg
    from versum.io import consume
    from versum.profile import get_profile
    import versum.profiles  # noqa: F401
    _cfg = cfg
    _reg = consume.read_registry(regcsv) if regcsv else None
    _prof = get_profile(profile_id)

def _do_domain(task):
    lib_id, lib_root, ns, dom, kg_root, scratch = task
    from versum.store.index import index_folder
    from versum import materialize
    t = time.time(); outv = os.path.join(scratch, dom, ".versum")
    try:
        m = index_folder(os.path.join(lib_root, dom), profile_id=_prof.id, out=outv,
                         consume=_reg, library=lib_id, namespace=ns, use_kg_provenance=False)
        materialize.materialize(os.path.join(scratch, dom),
                                os.path.join(kg_root, "by-domain", dom), library=lib_id)
        srcs = list(csv.DictReader(open(os.path.join(outv, "sources.csv"), encoding="utf-8")))
        shutil.rmtree(os.path.join(scratch, dom), ignore_errors=True)
        return {"dom": dom, "sources": m["n_sources"], "claims": m["n_claims"],
                "reuse": sum(1 for s in srcs if s["provenance"] == "kg-registry"),
                "mint": sum(1 for s in srcs if s["provenance"] == "minted"),
                "secs": round(time.time()-t, 1)}
    except Exception as e:
        shutil.rmtree(os.path.join(scratch, dom), ignore_errors=True)
        return {"dom": dom, "error": f"{type(e).__name__}: {e}", "secs": round(time.time()-t, 1)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    cfg, cfgpath = resolve_config(ap.parse_args().config)
    print(f"[migrate] config: {cfgpath}", flush=True)
    kg_root = cfg["kg_root"]; profile_id = cfg.get("profile_id", "generic")
    exclude = tuple(cfg.get("exclude_prefixes", ["_"]))
    scratch = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch")
    os.makedirs(os.path.join(kg_root, "by-domain"), exist_ok=True); os.makedirs(scratch, exist_ok=True)
    # the KG references each library by a root_path + relative paths (never copies the corpus)
    libjson = {L["id"]: {"root_path": L["root_path"], "urn_namespace": L["urn_namespace"],
                         "registry_path_prefix": L.get("registry_path_prefix", "")}
               for L in cfg["libraries"]}
    json.dump(libjson, open(os.path.join(kg_root, "libraries.json"), "w"), indent=2)
    done_f = os.path.join(kg_root, "_done_domains.txt")
    done = set(open(done_f).read().split()) if os.path.exists(done_f) else set()
    for L in cfg["libraries"]:
        root = L["root_path"]
        if not os.path.isdir(root):
            print(f"[migrate] SKIP library {L['id']}: root not found {root}", flush=True); continue
        domains = sorted(d for d in os.listdir(root)
                         if os.path.isdir(os.path.join(root, d)) and not d.startswith(exclude)
                         and f"{L['id']}/{d}" not in done)
        tasks = [(L["id"], root, L["urn_namespace"], d, kg_root, scratch) for d in domains]
        tot = {"library": L["id"], "domains": len(domains), "sources": 0, "claims": 0,
               "reuse": 0, "mint": 0, "errors": 0}
        print(f"[migrate] library {L['id']}: {len(domains)} domains; {cpu_count()} cores", flush=True)
        t0 = time.time()
        with Pool(processes=max(1, cpu_count()-1), initializer=_init,
                  initargs=(cfg, L.get("registry_csv"), profile_id)) as pool:
            for r in pool.imap_unordered(_do_domain, tasks):
                if "error" in r:
                    tot["errors"] += 1
                    open(os.path.join(kg_root, "_errors.log"), "a").write(f"{L['id']}/{r['dom']}: {r['error']}\n")
                    print(f"[migrate] ERROR {r['dom']}: {r['error']}", flush=True)
                else:
                    for k in ("sources", "claims", "reuse", "mint"): tot[k] += r[k]
                    print(f"[migrate] {r['dom']}: {r['sources']} src, {r['claims']} claims, "
                          f"reuse={r['reuse']} mint={r['mint']} ({r['secs']}s)", flush=True)
                done.add(f"{L['id']}/{r['dom']}"); open(done_f, "w").write("\n".join(sorted(done)))
                tot["elapsed_min"] = round((time.time()-t0)/60, 1)
                json.dump({**tot, "status": "RUNNING"}, open(os.path.join(kg_root, "_progress.json"), "w"), indent=2)
        json.dump({**tot, "status": "COMPLETE"}, open(os.path.join(kg_root, "_progress.json"), "w"), indent=2)
        print(f"[migrate] {L['id']} COMPLETE: {tot['sources']} sources, {tot['claims']} claims, "
              f"reuse={tot['reuse']} mint={tot['mint']} errors={tot['errors']} in {tot['elapsed_min']} min", flush=True)

if __name__ == "__main__":
    main()
