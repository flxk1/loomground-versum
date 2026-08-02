"""Loomground Versum CLI.

    python -m versum index   <folder> [--profile generic|law-eu] [--out DIR]
    python -m versum capture <folder> [--profile ...] [--consume-registry CSV]
                                      [--library ID] [--namespace NS]
    python -m versum watch   <folder> [--profile ...] [--interval 5]  # auto on add
    python -m versum models  <folder> <source-urn>
    python -m versum sources <folder> <concept-id>
    python -m versum export  <folder> [--format html|json|graphml] [--out PATH]

`index` builds/refreshes the graph from whatever is in the folder. `capture` runs the
deterministic guard (identity → dedup → stub+sidecar → index); idempotent, so re-running
after a document is dropped in admits only the new one. `watch` polls the folder and runs
`capture` whenever the file set changes. Everything persists in `<folder>/.versum/`.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .store import graph as g
from . import profiles as _profiles  # noqa: F401 — register built-ins
from .store.index import index_folder
from .write import CaptureError, capture_file, capture_folder


def _load(folder):
    v = Path(folder).resolve() / ".versum"
    claims = g.load_claims(v / "claims.csv") if (v / "claims.csv").exists() else []
    edges = g.load_edges(v / "semantic_edges.csv") if (v / "semantic_edges.csv").exists() else []
    return claims, edges


def _snapshot(folder) -> dict:
    """A cheap fingerprint of the folder's file set (path -> (mtime, size))."""
    folder = Path(folder).resolve()
    snap = {}
    for p in folder.rglob("*"):
        if p.is_file() and ".versum" not in p.parts and not any(
                part.startswith(".") for part in p.relative_to(folder).parts):
            st = p.stat()
            snap[p.as_posix()] = (int(st.st_mtime), st.st_size)
    return snap


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="versum", description="Loomground Versum")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("index"); pi.add_argument("folder")
    pi.add_argument("--profile", default="generic"); pi.add_argument("--out", default=None)
    pi.add_argument("--nd-system", action="append", default=[],
                    help="declarative nD system config (repeatable)")

    pc = sub.add_parser(
        "capture",
        help="admit, deduplicate, and index a folder (optionally reusing a KG registry)",
    )
    pc.add_argument("folder")
    pc.add_argument("--profile", default="generic")
    pc.add_argument(
        "--consume-registry",
        metavar="CSV",
        help="read a KG source_registry.csv and reuse matching canonical URNs",
    )
    pc.add_argument(
        "--library",
        metavar="ID",
        help="record the owning library ID on captured sources",
    )
    pc.add_argument(
        "--namespace",
        metavar="NS",
        help="URN namespace used when a source has no registry identity",
    )

    pcf = sub.add_parser("capture-file", help="admit one local source into a target folder")
    pcf.add_argument("source")
    pcf.add_argument("--target", required=True)
    pcf.add_argument("--profile", default="generic")

    pw = sub.add_parser("watch"); pw.add_argument("folder", nargs="?")
    pw.add_argument("--profile", default="generic")
    pw.add_argument("--interval", type=float, default=5.0)
    pw.add_argument("--config", default=None)  # Live Index: loop sync_once over a config

    # Live Index (config-driven, incremental, universal)
    psy = sub.add_parser("sync"); psy.add_argument("--config", required=True)
    psy.add_argument("--force-reextract", action="store_true",
                     help="re-extract every known file (cascades identity changes)")
    pse = sub.add_parser("seed-state"); pse.add_argument("--config", required=True)
    pre = sub.add_parser("replay-events", help="rebuild an empty KG from its K1 event log")
    pre.add_argument("--source", required=True, help="KG root containing _events.jsonl")
    pre.add_argument("--target", required=True, help="empty target KG root")
    prp = sub.add_parser("rebuild-projections", help="rebuild K3 projections in an empty root")
    prp.add_argument("--source", required=True, help="KG root containing event history")
    prp.add_argument("--target", required=True, help="empty target KG root")
    prp.add_argument("--config", default=None, help="optional sync config for canon settings")
    prp.add_argument("--m-max", type=int, default=1)
    pch = sub.add_parser("changes", help="read the K5 source-change feed")
    pch.add_argument("--kg-root", required=True)
    pch.add_argument("--since", type=int, default=0, help="last consumed event sequence")

    pg = sub.add_parser("suggest"); pg.add_argument("folder")   # curation: propose links
    pf = sub.add_parser("confirm"); pf.add_argument("folder")   # curation: promote
    pf.add_argument("--min-sources", type=int, default=1)
    pf.add_argument("--concepts", default=None,
                    help="comma-separated concept_ids to accept (curator's explicit "
                         "pick; overrides --min-sources)")

    # coordinate-identity curation (the mental-model / concept layer + domain canon)
    pcn = sub.add_parser("canon"); pcn.add_argument("--config", required=True)
    pcn.add_argument("--m-max", type=int, default=1)
    pcd = sub.add_parser("canon-domain"); pcd.add_argument("folder")
    pcd.add_argument("--m-max", type=int, default=1)

    # hybrid retrieval over a materialized KG (ADR-004)
    psr = sub.add_parser("search"); psr.add_argument("--config", required=True)
    psr.add_argument("--q", default=""); psr.add_argument("-k", type=int, default=10)
    psr.add_argument("--filter", action="append", default=[],
                     help="facet filter field=value (repeatable)")

    pm = sub.add_parser("models"); pm.add_argument("folder"); pm.add_argument("urn")
    ps = sub.add_parser("sources"); ps.add_argument("folder"); ps.add_argument("concept_id")

    pex = sub.add_parser("export", help="export the graph for viewers")
    pex.add_argument("folder")
    pex.add_argument("--format", default="html", choices=("html", "json", "graphml"),
                     help="html = self-contained offline viewer; json = versum_graph/v1 "
                          "payload; graphml = Gephi/Cytoscape")
    pex.add_argument("--out", default=None, help="output path (default: .versum/graph.<ext>)")

    pn = sub.add_parser("validate-nd", help="validate declarative user nD systems")
    pn.add_argument("configs", nargs="+")

    # provenance-first product intake
    ping = sub.add_parser("ingest"); ping.add_argument("item")
    ping.add_argument("--inbox", required=True); ping.add_argument("--profile", default="generic")
    pipr = sub.add_parser("inbox-process"); pipr.add_argument("--inbox", required=True)
    pipr.add_argument("--review", required=True); pipr.add_argument("--profile", default="generic")
    pia = sub.add_parser("inbox-audit"); pia.add_argument("--inbox", required=True)

    # universal language/system adapters
    pad = sub.add_parser("adapt", help="project a canonical system observation into Graph-Versum")
    pad.add_argument("--adapter", required=True, choices=("loomground",))
    pad.add_argument("--observation", required=True)
    pad.add_argument("--out", required=True)

    args = ap.parse_args(argv)

    if args.cmd == "capture-file":
        try:
            report = capture_file(args.source, args.target, args.profile)
        except CaptureError as exc:
            print(json.dumps({"status": "error", "error": exc.code,
                              "message": str(exc)}, ensure_ascii=False))
            return exc.exit_code
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "index":
        print(json.dumps(index_folder(args.folder, args.profile, args.out,
                                      nd_system_paths=args.nd_system),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "capture":
        if args.consume_registry:
            from .io.consume import read_registry
            consume = read_registry(args.consume_registry)
        else:
            consume = None
        r = capture_folder(
            args.folder,
            args.profile,
            namespace=args.namespace,
            consume=consume,
            library=args.library,
        )
        r.pop("admitted", None); r.pop("duplicates", None)  # keep the print compact
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif args.cmd == "watch" and args.config:
        from .sync import load_config, watch
        return watch(load_config(args.config))
    elif args.cmd == "watch":
        if not args.folder:
            ap.error("watch needs a <folder> or --config")
        print(f"watching {Path(args.folder).resolve()} every {args.interval}s "
              f"(profile={args.profile}); Ctrl-C to stop")
        last = None
        while True:
            snap = _snapshot(args.folder)
            if snap != last:
                r = capture_folder(args.folder, args.profile)
                print(json.dumps({"changed": True, "n_admitted": r["n_admitted"],
                                  "n_claims": r["index"]["n_claims"]}, ensure_ascii=False))
                last = snap
            time.sleep(args.interval)
    elif args.cmd == "export":
        from .export import export
        print(json.dumps(export(args.folder, args.format, args.out),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "sync":
        from .sync import load_config, sync_once
        print(json.dumps(sync_once(load_config(args.config),
                                   force_reextract=args.force_reextract),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "seed-state":
        from .sync import load_config, seed_state
        print(json.dumps(seed_state(load_config(args.config)), ensure_ascii=False, indent=2))
    elif args.cmd == "replay-events":
        from .events import replay_event_log
        print(json.dumps(replay_event_log(args.source, args.target),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "rebuild-projections":
        from .projections import rebuild_projections
        from .sync import load_config
        config = load_config(args.config) if args.config else None
        print(json.dumps(rebuild_projections(args.source, args.target, config, args.m_max),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "changes":
        from .events import changes_since
        print(json.dumps(changes_since(args.kg_root, args.since),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "suggest":
        from .concept.curate import suggest_folder
        print(json.dumps(suggest_folder(args.folder), ensure_ascii=False, indent=2))
    elif args.cmd == "confirm":
        from .concept.curate import confirm_folder
        picked = ({c.strip() for c in args.concepts.split(",") if c.strip()}
                  if args.concepts else None)
        print(json.dumps(confirm_folder(args.folder, args.min_sources, picked),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "canon":
        from .concept.canon import curate_kg
        print(json.dumps(curate_kg(args.config, m_max=args.m_max),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "canon-domain":
        from .concept.canon import curate_domain_folder
        print(json.dumps(curate_domain_folder(args.folder, m_max=args.m_max),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "search":
        from .sync import load_config
        from .store.retrieve import from_kg
        cfg = load_config(args.config)
        filters = dict(f.split("=", 1) for f in args.filter if "=" in f)
        idx = from_kg(cfg["kg_root"])
        print(json.dumps(idx.search(args.q, filters=filters, k=args.k),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "models":
        claims, edges = _load(args.folder)
        print(json.dumps(sorted(g.models_for_source(args.urn, claims, edges))))
    elif args.cmd == "sources":
        claims, edges = _load(args.folder)
        print(json.dumps(sorted(g.sources_for_model(args.concept_id, claims, edges))))
    elif args.cmd == "validate-nd":
        from .nd import NDRegistry
        registry = NDRegistry(include_core=True).load(args.configs)
        print(json.dumps(registry.manifest(), ensure_ascii=False, indent=2))
    elif args.cmd == "ingest":
        from .ingestion.route import producer_ingest
        print(json.dumps(producer_ingest(args.item, args.inbox, args.profile),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "inbox-process":
        from .ingestion.pipeline import process
        print(json.dumps(process(args.inbox, args.review, args.profile),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "inbox-audit":
        from .ingestion.pipeline import audit
        result = audit(args.inbox)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if any(result["acquire"].values()) or any(result["provenance"].values()):
            return 1
    elif args.cmd == "adapt":
        from .adapters import save_projection
        if args.adapter == "loomground":
            from .integrations.loomground import LoomgroundAdapter
            adapter = LoomgroundAdapter()
        observation = json.loads(Path(args.observation).read_text(encoding="utf-8"))
        projection = adapter.import_observation(observation)
        output = save_projection(args.out, projection)
        print(json.dumps({
            "adapter": projection.identity.adapter_id,
            "system": projection.identity.system_id,
            "system_version": projection.identity.version,
            "nodes": len(projection.nodes),
            "relations": len(projection.relations),
            "assignments": len(projection.assignments),
            "bindings": len(projection.bindings),
            "out": str(output.resolve()),
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
