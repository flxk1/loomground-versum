#!/usr/bin/env python3
"""remediate_stub_provenance.py — repair a KG store that minted parallel URNs for
KG citation stubs / sidecar-carried sources (Live Index sidecar fix, 2026-08).

BACKGROUND. Before the fix, `versum sync` resolved identity from the library registry
CSV only and never consulted KG capture sidecars (`*.md.metadata.json`). Two failure
modes in an affected store:

  1. **Stubs indexed as sources.** A citation stub (a `.md` with a paired sidecar) was
     claim-extracted under a freshly minted `urn:<ns>:sha256:...` — a parallel provenance
     record for a source whose sidecar already carries the authoritative `canonical_urn`.
  2. **Sidecar identity ignored on kept sources.** A non-stub file with a paired sidecar
     (or a deterministic folder-sidecar match) was indexed under a minted URN instead of
     the sidecar's `canonical_urn`.

SANCTIONED REPAIR. The engine treats a URN change as a deliberate sidecar override that
is CASCADED BY RE-INDEXING — never by hand-editing store CSVs. With the fixed engine:

  * a previously indexed stub no longer appears on the library walk, so the next sync
    pass classifies it as *removed* and drops exactly its own rows (claims keyed on its
    recorded canonical_urn, its fingerprint, its sources.csv row) — the corpus file is
    untouched;
  * a kept source whose identity now resolves to a sidecar URN is byte-unchanged, so it
    needs a FORCED pass: `sync_once(cfg, force_reextract=True)` re-runs every known file
    through the *changed* path, which first removes the rows keyed on the OLD recorded
    canonical_urn and then re-appends under the sidecar's — no orphan rows remain, and
    the K1 event log records the removal + upsert pair per source.

THIS SCRIPT audits by default (READ-ONLY, prints the repair plan) and only performs the
repair with an explicit `--apply`, which runs the sanctioned forced sync pass. It never
writes a store row itself. Equivalent manual repair once the fixed engine is deployed:

    python -m versum sync --config <config> --force-reextract

Run:   python3 remediate_stub_provenance.py --config /path/to/loomground-kg.config.json
       python3 remediate_stub_provenance.py --config ... --apply
Config resolves from: --config > $LOOMGROUND_KG_CONFIG > ./loomground-kg.config.json >
<this dir>/loomground-kg.config.json. Engine: $VERSUM_ENGINE > repository checkout.
"""
import sys, os, json, argparse
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))


def resolve_config(arg):
    for cand in [arg, os.environ.get("LOOMGROUND_KG_CONFIG"),
                 os.path.join(os.getcwd(), "loomground-kg.config.json"),
                 os.path.join(HERE, "loomground-kg.config.json")]:
        if cand and os.path.exists(cand):
            return cand
    sys.exit("No config found. Pass --config <path> or set LOOMGROUND_KG_CONFIG.")


ENGINE = os.environ.get("VERSUM_ENGINE", str(Path(HERE).parents[1]))
sys.path.insert(0, os.path.join(ENGINE, "src"))


def audit(cfg: dict) -> dict:
    """READ-ONLY: classify every recorded state entry against the FIXED identity rules.

    Returns per-library lists:
      * ``stubs``    — recorded entries whose file is now a KG citation stub on disk;
        the next plain sync pass drops their rows via the *removed* path.
      * ``drifted``  — kept files whose resolved canonical_urn differs from the recorded
        one (e.g. a sidecar now settles it); needs the forced pass to cascade.
      * ``deleted``  — recorded entries whose file is gone from disk entirely (ordinary
        removals, listed for completeness).
    """
    import versum.profiles  # noqa: F401 — register built-in profiles
    from versum import sync as vs
    from versum.store import kg
    from versum.profile import get_profile

    state = vs.SyncState(cfg["kg_root"])
    profile = get_profile(cfg.get("profile_id", "generic"))
    report = {"kg_root": cfg["kg_root"], "libraries": []}
    for lib in cfg.get("libraries", []):
        lib_id = lib["id"]
        root = Path(lib["root_path"]).resolve()
        namespace = lib.get("urn_namespace")
        reg_prefix = lib.get("registry_path_prefix") or ""
        reg = vs._resolve_registry(lib)
        sidecars = kg.load_sidecars(root)
        disk = vs._walk(root, lib.get("exclude_prefixes", ["_"]))  # stub-free by design

        stubs, drifted, deleted = [], [], []
        prefix = lib_id + "::"
        for key, entry in sorted(state.files.items()):
            if not key.startswith(prefix):
                continue
            rel = key[len(prefix):]
            recorded = entry.get("canonical_urn", "")
            info = disk.get(rel)
            if info is None:
                abspath = root / rel
                if abspath.is_file() and kg.is_kg_stub(abspath, root):
                    stubs.append({"relpath": rel, "recorded_urn": recorded,
                                  "sidecar_urn": vs._paired_sidecar_urn(abspath)})
                else:
                    deleted.append({"relpath": rel, "recorded_urn": recorded})
                continue
            match_rel = (reg_prefix + rel) if reg_prefix else rel
            resolved, provenance = vs._resolve_identity(
                reg, match_rel, info["abspath"].name, info["abspath"], profile,
                namespace, sidecars)
            if resolved != recorded:
                drifted.append({"relpath": rel, "recorded_urn": recorded,
                                "resolved_urn": resolved, "provenance": provenance})
        report["libraries"].append({
            "library": lib_id, "stubs": stubs, "drifted": drifted, "deleted": deleted,
            "n_stubs": len(stubs), "n_drifted": len(drifted), "n_deleted": len(deleted),
        })
    report["needs_plain_sync"] = any(x["n_stubs"] or x["n_deleted"]
                                     for x in report["libraries"])
    report["needs_forced_sync"] = any(x["n_drifted"] for x in report["libraries"])
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=None)
    ap.add_argument("--apply", action="store_true",
                    help="perform the sanctioned repair (forced sync pass); "
                         "default is a read-only audit")
    args = ap.parse_args()

    cfg_path = resolve_config(args.config)
    from versum.sync import load_config, sync_once
    cfg = load_config(cfg_path)

    plan = audit(cfg)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not args.apply:
        if plan["needs_plain_sync"] or plan["needs_forced_sync"]:
            mode = ("--force-reextract" if plan["needs_forced_sync"] else "(plain)")
            print(f"\nDRY RUN — nothing written. Repair with: --apply  "
                  f"[equivalent: python -m versum sync --config {cfg_path} {mode}]",
                  file=sys.stderr)
        else:
            print("\nDRY RUN — store already consistent; nothing to repair.",
                  file=sys.stderr)
        return 0

    # The sanctioned cascade: one forced pass. Stubs drop via the removed path;
    # drifted identities replace their OWN old rows then re-append; the event log
    # records every removal/upsert. No store CSV is ever hand-edited.
    force = bool(plan["needs_forced_sync"])
    r = sync_once(cfg, force_reextract=force)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
