# Dimensioned-subgraph ingestion contract

`versum.ingestion.DimensionedSubgraphSink` is Versum's public, versioned sink for the
Ingestor → Versum edge. It accepts only
`loomground.versum.dimensioned-subgraph/v1` envelopes.

An envelope carries:

- an idempotency key and source content digest;
- evidence identities bound to that source;
- typed nodes and relations;
- an explicit `5D` or `nD` facet, nD system, dimension count, and axes;
- optional node coordinates that may only name declared axes;
- typed node-or-literal endpoints, evidence references, and a declared dimension on every
  relation.

Unknown fields, schemas, identities, endpoints, axes, digests, or evidence references fail
closed. The caller must provide an authorized store root; the target store is resolved and
must remain contained by it.

Each upsert publishes one complete canonical transaction with one exclusive atomic
filesystem link under `_dimensioned_subgraph_transactions/`. Retrying the same key and content returns an
`unchanged` receipt. Reusing a key with different content raises
`IdempotencyConflictError`.

This transaction is the persistence record. It does not call
`versum.adapters.save_projection`: adapter projection files are separate import/export
read models and are not a graph ingestion door.
