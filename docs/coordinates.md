# Coordinate queries

`versum.coordinates` answers two questions over an already-indexed store (a
`versum index`/`capture` folder, i.e. a folder that carries a `.versum/` directory —
or that `.versum/` directory itself):

* "what is entry X's full coordinate record?" — `entry_coordinates`
* "which entries sit at this nD coordinate?" — `entries_in_cell`

Stdlib only. Both read the store through the public, already-typed readers wherever one
exists (`versum.nd.load_assignments` for `nd/assignments.csv`, and the run's own nD
registry manifest, `nd/systems.json`, as the fail-closed authority on which systems and
axes exist); `entries.csv` / `entry_claims.jsonl` carry no typed/encoded columns of
their own, so they are read directly with the stdlib `csv`/`json` modules, exactly as
`versum.store.index.index_folder` writes them. See `docs/nd-on-index.md` for what those
files contain and the 5D-is-what-IS / O-P-F-are-OUGHT binding this module's `dimension`
field observes.

## Python API

```python
from versum.coordinates import entry_coordinates, entries_in_cell

entry_coordinates(store, entry_id) -> dict
entries_in_cell(store, cell: dict) -> list[str]
```

### `entry_coordinates(store, entry_id)`

Returns:

```python
{
    "entry_id": str,
    "dimension": str | None,   # the entry's 5D dominant dimension, or None for an
                                # OUGHT/norm entry (an operator O/P/F is a normative
                                # force, never a fact on the 5D manifold — never a
                                # fabricated dimension)
    "nd": {system_id: {axis_id: value}},   # value is a list when the axis carries
                                             # more than one value for this entry
    "span": (start: int, end: int, text: str),   # the entry's exact offsets/slice as
                                                   # versum's own entries.csv records
                                                   # them
    "source_urn": str,
}
```

A norm entry's own deontic `action` coordinate is a **reference**: the action-type
entry's own `item_id`, never the literal action text a second time (see
`docs/nd-on-index.md`, "5D is what IS").

Raises `UnknownEntryError` (a `KeyError` subclass) if `entry_id` is not in the store's
`entries.csv`. Never returns a default/empty record for an entry the store does not
have.

`nd` includes the entry's source-level core coordinates (`jurisdiction`, `time`) as well
as its own plane assignments: those two are written once per source URN, never once per
entry (see `docs/nd-on-index.md`), and this function joins them onto every entry of that
source — the same join `versum.planes.entry_coordinates` performs for the plane pipeline
itself.

### `entries_in_cell(store, cell)`

`cell` is `{system_id: {axis_id: value, ...}, ...}` — every system, and every axis
within a system, is ANDed together; a many-valued axis matches if `value` is among the
entry's assigned values for it. Returns a `list[str]` of entry ids (`item_id`s — not
full coordinate dicts), in deterministic reading order:
`(source_urn, span_start, span_end, entry_id)`.

Raises `UnknownSystemError` for a system id absent from the store's nD registry
(`nd/systems.json`), or `UnknownAxisError` for an axis id not declared on an
otherwise-known system — checked against the registry **before** any row is scanned, so
an unknown system/axis raises even when the rest of the query would have matched zero
rows. Never returns `[]` silently for an unknown system/axis.

A `jurisdiction`/`time` constraint (`versum-context`) matches every entry of a source
that carries it, not just a subject whose own `item_id` was assigned it directly — those
two axes are written once per source URN (see `docs/nd-on-index.md`), and this function
joins them onto the source's entries the same way `entry_coordinates` (above) does.

### Exceptions

```python
class VersumCoordinateError(KeyError):   # base; every one of these IS a KeyError
class UnknownEntryError(VersumCoordinateError): ...
class UnknownSystemError(VersumCoordinateError): ...
class UnknownAxisError(VersumCoordinateError): ...
```

All four are importable from `versum` directly (`from versum import entry_coordinates,
entries_in_cell, UnknownEntryError, UnknownSystemError, UnknownAxisError,
VersumCoordinateError`) as well as from `versum.coordinates`.

## CLI

```bash
versum coords <store> <entry-id>
versum cell   <store> --where SYSTEM.AXIS=VALUE [--where SYSTEM.AXIS=VALUE ...]
```

Both print the JSON result (the same shapes as the Python API — `cell`'s "value" is a
bare JSON array of entry-id strings) to stdout and exit `0`. On a fail-closed error
(unknown entry / system / axis) they print a `{"status": "error", "error": <exception
class name>, "message": ...}` object to stderr and exit non-zero (`2`).

`--where` values are parsed as JSON when possible (so `--where
loomground-deontic.negated=false` matches the boolean `false`, not the string
`"false"`), falling back to the raw string otherwise (so `--where
loomground-deontic.operator=O` matches the string `"O"`).

### Worked example (the `credit_policy_nd` fixture)

```bash
versum index tests/fixtures/credit_policy_nd --profile law-eu --out /tmp/store
versum coords /tmp/store <article-3-norm-entry-id>
# {
#   "entry_id": "ent-...",
#   "dimension": null,
#   "nd": {"loomground-deontic": {"operator": "O", "bearer": "reviewer",
#          "action": "ent-...", "condition": "before it is sent", "negated": false}},
#   "span": [163, 222, "A reviewer shall examine every rejection before it is sent."],
#   "source_urn": "urn:dls:sha256:..."
# }

versum cell /tmp/store --where loomground-deontic.operator=O
# ["ent-<article-3-norm>", "ent-<article-4-norm>"]
```
