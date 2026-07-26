# Projection authority and rebuilding

Versum classifies persisted structures by authority before allowing them to be rebuilt.
The machine-readable classification is returned by `projection_contract()` and written to
`<kg_root>/_projections/manifest.json` during a rebuild.

Disposable projections are:

- the K1 event materialization (`by-domain/`, sync state, nD manifest, graph version),
- deterministic coordinate-canon tables and summaries,
- the portable search document snapshot; facet postings and BM25 statistics rebuild in
  memory whenever that snapshot is loaded.

Confirmed `.versum/concepts.csv` and `.versum/semantic_edges.csv` produced by the
suggest/confirm workflow are protected inputs. Confirmation records a curator decision and
is not a cache. The projection rebuild never reads, overwrites, or deletes those files.

To rebuild all deterministic KG projections without risking the working root:

```bash
versum rebuild-projections --source /path/to/kg --target /path/to/empty-root \
  --config /path/to/versum-config.json
```

The command validates and replays K1 history into the empty target, regenerates the
coordinate canon from claim rows, and regenerates the search snapshot. This target-first
design makes the rebuilt result inspectable before any deployment or directory swap.
