"""Coordinate queries over an indexed store: one entry's full position, and the
entries occupying a given nD cell.

Two functions, stdlib only:

* :func:`entry_coordinates` — one entry's 5D dimension (or ``None`` for an OUGHT/norm
  entry — 5D is what IS; an operator carries no 5D dimension under any name, see
  ``docs/nd-on-index.md``), its nD coordinate assignments grouped by system, its exact
  span into the source text, and its source URN.
* :func:`entries_in_cell` — the entry ids whose nD assignments satisfy every
  ``{system_id: {axis_id: value}}`` constraint given.

Both read an already-indexed store (``versum index``/``index_folder`` output: a
``<store>/.versum/`` directory, or that directory itself) through the public,
already-typed readers wherever one exists — :func:`versum.nd.load_assignments` for
``nd/assignments.csv`` (it parses the JSON-encoded ``value`` column; this module never
re-implements that) — plus the run's own nD registry manifest (``nd/systems.json``, the
same document :meth:`versum.nd.NDRegistry.manifest` writes) as the fail-closed
authority on which systems/axes exist. ``entries.csv`` and ``entry_claims.jsonl`` carry
no typed/encoded columns of their own (plain strings and a plain JSON-lines log,
exactly as :func:`versum.store.index.index_folder` writes them), so they are read here
directly with the stdlib ``csv``/``json`` modules — not reinterpreted, not re-encoded.

**Source-scoped axes join onto their entries.** A core coordinate (``jurisdiction``,
``time``) is written once per source, with ``subject_id`` set to the *source URN*, never
to an entry's ``item_id`` (see ``versum.store.index.index_folder`` and
``docs/nd-on-index.md``): it "applies to every entry of that source" rather than being
repeated on each one. Both functions in this module read that the same way
:func:`versum.planes.entry_coordinates` (the shared per-entry/source join helper the
plane pipeline itself uses internally) does: an entry's full coordinate set is its own
``item_id``-keyed rows UNION its source's ``source_urn``-keyed rows. Concretely,
``entries_in_cell({"versum-context": {"jurisdiction": "EU"}})`` returns the *entries* of
every source whose jurisdiction is ``"EU"`` — not an empty list, and not the source URNs
themselves (:func:`entries_in_cell` only ever returns entry ids). This is the join this
module chose (over leaving the gap merely documented): a query naming a real, populated
axis on a real, populated system must find the entries a human would expect it to,
whichever level of the store actually carries that axis's rows.

Fails closed. Never returns an empty/default result for a query this module cannot
actually answer:

* :class:`UnknownEntryError` — ``entry_id`` is not in the store's ``entries.csv``.
* :class:`UnknownSystemError` — a queried nD system id is not in the store's registry.
* :class:`UnknownAxisError` — a queried axis id is not declared on an otherwise-known
  system.

All three are :class:`KeyError` subclasses (via the shared
:class:`VersumCoordinateError` base), so ``except KeyError`` also catches them; catch
the specific subclass to tell the three cases apart.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from . import planes as _planes
from .nd import load_assignments

__all__ = [
    "VersumCoordinateError",
    "UnknownEntryError",
    "UnknownSystemError",
    "UnknownAxisError",
    "entry_coordinates",
    "entries_in_cell",
]

# The plane id the deontic language pack's descriptor registers under (see
# ``versum.deontic.DEONTIC_PLANE_ID``); named here, not imported, so this module never
# requires the deontic package to be installed just to read an already-written store.
_DEONTIC_PLANE_ID = "deontic"


class VersumCoordinateError(KeyError):
    """Base for the fail-closed coordinate-query errors in this module (a ``KeyError``
    subclass: every one of these means "that key does not exist in this store")."""


class UnknownEntryError(VersumCoordinateError):
    """``entry_id`` is not present in the store's ``entries.csv``."""


class UnknownSystemError(VersumCoordinateError):
    """A queried nD system id is not registered in the store's ``nd/systems.json``."""


class UnknownAxisError(VersumCoordinateError):
    """A queried axis id is not declared on an otherwise-known nD system."""


def _versum_dir(store) -> Path:
    """Accept either a folder indexed by ``versum index``/``capture``, or its
    ``.versum/`` directory directly."""
    p = Path(store)
    inner = p / ".versum"
    return inner if inner.is_dir() else p


def _load_entries(versum_dir: Path) -> dict[str, dict]:
    path = versum_dir / "entries.csv"
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        for key in ("span_start", "span_end"):
            if row.get(key) not in (None, ""):
                row[key] = int(row[key])
    return {row["item_id"]: row for row in rows}


def _load_entry_claims(versum_dir: Path) -> dict[str, list[dict]]:
    path = versum_dir / "entry_claims.jsonl"
    out: dict[str, list[dict]] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out.setdefault(row["item_id"], []).append(row)
    return out


def _load_registry(versum_dir: Path) -> dict[str, set[str]]:
    """``system_id -> {bare axis ids}``, from the run's own nD registry manifest
    (``nd/systems.json``, written by :meth:`versum.nd.NDRegistry.manifest`)."""
    path = versum_dir / "nd" / "systems.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    registry: dict[str, set[str]] = {}
    for system in manifest.get("systems", []):
        axes = set()
        for qualified in system.get("axes", []):
            _namespace, _sep, axis_id = qualified.partition(":")
            axes.add(axis_id if _sep else qualified)
        registry[system["id"]] = axes
    return registry


def _is_ought_entry(item_id: str, claims_by_entry: dict[str, list[dict]]) -> bool:
    """True iff this entry carries the deontic plane's own claim: an operator (O/P/F)
    is a normative force, never a fact on the 5D manifold (see ``versum.planes``
    ``build_source_entries``, decision D1) — its entry's ``dimension`` must be reported
    as ``None``, never the structural artefact its ``embeds`` link happens to leave on
    ``entries.csv``."""
    return any(claim.get("plane") == _DEONTIC_PLANE_ID
              for claim in claims_by_entry.get(item_id, ()))


def entry_coordinates(store, entry_id: str) -> dict:
    """One entry's full coordinate record.

    Returns a dict shaped::

        {
            "entry_id": str,
            "dimension": str | None,   # the 5D dominant dimension, or None for an
                                        # OUGHT/norm entry (never fabricated)
            "nd": {system_id: {axis_id: value}},   # value is a list when an axis
                                                     # carries more than one value
            "span": (start: int, end: int, text: str),
            "source_urn": str,
        }

    Raises :class:`UnknownEntryError` if ``entry_id`` is not in the store.
    """
    versum_dir = _versum_dir(store)
    entries = _load_entries(versum_dir)
    entry = entries.get(entry_id)
    if entry is None:
        raise UnknownEntryError(f"unknown entry id {entry_id!r}")

    claims_by_entry = _load_entry_claims(versum_dir)
    dimension = (None if _is_ought_entry(entry_id, claims_by_entry)
                else entry["dominant_dimension"])

    nd: dict[str, dict[str, Any]] = {}
    all_assignments = load_assignments(versum_dir / "nd" / "assignments.csv")
    # entry-scoped rows UNION this entry's source-scoped rows (jurisdiction/time) — the
    # same join versum.planes.entry_coordinates applies for the plane pipeline itself.
    for row in _planes.entry_coordinates(entry, all_assignments):
        by_axis = nd.setdefault(row["system_id"], {})
        axis_id, value = row["axis_id"], row["value"]
        if axis_id in by_axis:
            existing = by_axis[axis_id]
            values = existing if isinstance(existing, list) else [existing]
            values.append(value)
            by_axis[axis_id] = sorted(values, key=lambda v: json.dumps(v, sort_keys=True))
        else:
            by_axis[axis_id] = value

    return {
        "entry_id": entry_id,
        "dimension": dimension,
        "nd": nd,
        "span": (entry["span_start"], entry["span_end"], entry["text"]),
        "source_urn": entry["source_urn"],
    }


def entries_in_cell(store, cell: dict) -> list[str]:
    """Entry ids whose nD assignments satisfy every constraint in ``cell``
    (``{system_id: {axis_id: value}}``; every system, and every axis within a system,
    is ANDed together — a many-valued axis matches if ``value`` is among the entry's
    assigned values for it). An entry's assigned values include its source's core
    ``jurisdiction``/``time`` coordinates (see the module docstring's "Source-scoped axes
    join onto their entries"): those rows are written once per source URN, never per
    entry, so a cell naming one of them matches every entry of a source carrying it.

    Returns a list of entry ids (``item_id`` strings, not full coordinate dicts), in
    deterministic reading order: ``(source_urn, span_start, span_end, entry_id)``.

    Raises :class:`UnknownSystemError` for a system id absent from the store's nD
    registry, or :class:`UnknownAxisError` for an axis id not declared on an
    otherwise-known system — checked against the registry up front, so a cell that
    names an unknown system/axis raises even when zero rows would have matched it.
    """
    versum_dir = _versum_dir(store)
    registry = _load_registry(versum_dir)
    for system_id, axes in cell.items():
        if system_id not in registry:
            raise UnknownSystemError(f"unknown nD system {system_id!r}")
        known_axes = registry[system_id]
        for axis_id in axes:
            if axis_id not in known_axes:
                raise UnknownAxisError(
                    f"unknown axis {axis_id!r} for nD system {system_id!r}")

    by_subject: dict[str, dict[tuple[str, str], list]] = {}
    for row in load_assignments(versum_dir / "nd" / "assignments.csv"):
        key = (row["system_id"], row["axis_id"])
        by_subject.setdefault(row["subject_id"], {}).setdefault(key, []).append(row["value"])

    entries = _load_entries(versum_dir)
    matches = []
    for entry_id, entry in entries.items():
        # entry-scoped rows UNION this entry's source-scoped rows (jurisdiction/time
        # apply to every entry of a source, never repeated per-entry on disk) — same
        # join versum.planes.entry_coordinates applies for the plane pipeline itself.
        axis_values: dict[tuple[str, str], list] = {}
        for subject_id in {entry_id, entry.get("source_urn")}:
            for key, values in by_subject.get(subject_id, {}).items():
                axis_values.setdefault(key, []).extend(values)
        ok = True
        for system_id, axes in cell.items():
            for axis_id, value in axes.items():
                values = axis_values.get((system_id, axis_id))
                if values is None or value not in values:
                    ok = False
                    break
            if not ok:
                break
        if ok:
            matches.append(entry_id)

    def sort_key(item_id: str):
        entry = entries[item_id]
        return (entry["source_urn"], entry["span_start"], entry["span_end"], item_id)

    return sorted(matches, key=sort_key)
