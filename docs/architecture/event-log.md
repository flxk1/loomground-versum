# Event history and replay

Versum's config-driven KG has one mutation history: `<kg_root>/_events.jsonl`. Each line
is an immutable `loomground.versum.event/v1` record. New mutations append new lines;
Versum never edits or truncates an existing event.

The log records an ordered sequence number, content-derived event ID, mutation and object
types, stable object ID, prior and new payload digests, UTC observation time, affected
claim IDs, and the complete replay payload. Per-object digest chains make deleted and
re-created sources explicit and cause corrupt or reordered history to fail closed.

The following files are materialized projections, not independent sources of truth:

- `by-domain/`
- `_sync_state.json`
- `_nd_systems.json`
- `_graph_version.json`

The current event types are `source.upserted`, `source.removed`, `source.seeded`, and
`nd.manifest.updated`. When a pre-K1 store is opened for the first time, Versum also writes
one `projection.baseline` event containing its existing materialization; this makes upgrades
replayable without changing working KG data. A changed source is deliberately represented as a removal followed
by an upsert, so history preserves both the invalidated claim IDs and the replacement.
A sync that observes no semantic or inventory change appends nothing.

To validate a history and rebuild all projections into a target that contains no Versum
state:

```bash
versum replay-events --source /path/to/kg --target /path/to/empty-replica
```

Replay regenerates the projections, mints the graph version from their semantic content,
and copies the validated history byte-for-byte. The resulting projection bytes and graph
version must equal those of the source. Projection writers may replace their own files;
only the event log carries the no-rewrite guarantee.

Appending precedes projection mutation. If a process stops between those operations, the
durable event remains available for replay. Filesystem-level atomicity across the log and
all projections is not claimed; recovery is deterministic replay into an empty root.

Consumers can incrementally invalidate their own derivations using the ordered K5 feed:

```bash
versum changes --kg-root /path/to/kg --since 42
```

The returned watermark is the latest validated event sequence. `changes` groups affected
claim IDs by canonical URN and excludes seed, manifest, baseline, and unchanged-source
activity. A consumer persists the returned watermark only after processing the delta.
