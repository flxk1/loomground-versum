"""Validated persistence for claim-grounded compositions and nD context."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..composition import Composition, load_compositions, save_compositions
from ..store.graph import load_claims
from ..nd import (
    Binding, CoordinateAssignment, NDSystem, load_assignments, load_bindings,
    save_assignments, save_bindings,
)


def _root(path) -> Path:
    value = Path(path).expanduser().resolve()
    return value if value.name == ".versum" else value / ".versum"


def _merge(existing, incoming, key, label):
    rows = {key(row): row for row in existing}
    for row in incoming:
        identity = key(row)
        previous = rows.get(identity)
        if previous is not None and previous != row:
            raise ValueError(f"{label} id {identity!r} already identifies different content")
        rows.setdefault(identity, row)
    return list(rows.values())


def persist_claim_semantics(path, *, compositions=(), systems=(), assignments=(), bindings=()):
    """Merge native semantic records after validating their claim grounding.

    The function is a transaction boundary, not another graph model: callers
    provide Versum ``Composition``, ``NDSystem``, ``CoordinateAssignment`` and
    ``Binding`` records directly. All validation completes before any file is
    changed, and repeated admission is idempotent.
    """
    root = _root(path)
    claim_path = root / "claims.csv"
    if not claim_path.is_file():
        raise FileNotFoundError(f"Versum claim store not found at {claim_path}")
    claim_ids = {str(row.get("item_id") or "") for row in load_claims(claim_path)}

    incoming_compositions = [
        row if isinstance(row, Composition) else Composition.from_dict(row)
        for row in compositions
    ]
    for composition in incoming_compositions:
        errors = composition.violations()
        if errors:
            raise ValueError("invalid composition: " + "; ".join(errors))
        evidence = {str(value) for participant in composition.participants
                    for value in participant.evidence_ids}
        missing = sorted(evidence - claim_ids)
        if missing:
            raise ValueError(
                f"composition {composition.composition_id!r} cites unknown claims {missing}")

    incoming_systems = list(systems)
    system_map = {(system.system_id, system.version): system.validate()
                  for system in incoming_systems}
    incoming_assignments = list(assignments)
    for assignment in incoming_assignments:
        system = system_map.get((assignment.system_id, assignment.system_version))
        if system is None:
            raise ValueError(f"assignment {assignment.assignment_id!r} names an unknown nD system")
        errors = assignment.violations(system)
        if errors:
            raise ValueError("invalid assignment: " + "; ".join(errors))
        if assignment.subject_id not in claim_ids:
            raise ValueError(
                f"assignment {assignment.assignment_id!r} cites unknown claim "
                f"{assignment.subject_id!r}")

    incoming_bindings = list(bindings)
    assignment_ids = {assignment.assignment_id for assignment in incoming_assignments}
    for binding in incoming_bindings:
        matching = [system for system in incoming_systems if binding.axis_id in system.axes]
        if not matching:
            raise ValueError(f"binding {binding.binding_id!r} names an unknown nD axis")
        errors = binding.violations(matching[0])
        if errors:
            raise ValueError("invalid binding: " + "; ".join(errors))
        if binding.claim_id not in claim_ids:
            raise ValueError(f"binding {binding.binding_id!r} cites unknown claim")
        if binding.assignment_id not in assignment_ids:
            raise ValueError(f"binding {binding.binding_id!r} cites unknown assignment")

    merged_compositions = _merge(
        load_compositions(root / "compositions.jsonl"), incoming_compositions,
        lambda row: row.composition_id, "composition")
    merged_assignments = _merge(
        [CoordinateAssignment(**row) for row in load_assignments(root / "nd" / "assignments.csv")],
        incoming_assignments, lambda row: row.assignment_id, "assignment")
    merged_bindings = _merge(
        [Binding(**row) for row in load_bindings(root / "nd" / "bindings.csv")],
        incoming_bindings, lambda row: row.binding_id, "binding")

    system_files = []
    systems_root = root / "nd" / "systems"
    for system in incoming_systems:
        target = systems_root / f"{system.system_id}-{system.version}.json"
        content = json.dumps({"nd_system": asdict(system)}, ensure_ascii=False,
                             indent=2, sort_keys=True) + "\n"
        if target.exists() and target.read_text(encoding="utf-8") != content:
            raise ValueError(f"nD system {system.system_id!r} already differs")
        system_files.append((target, content))

    save_compositions(root / "compositions.jsonl", merged_compositions)
    save_assignments(root / "nd" / "assignments.csv", merged_assignments)
    save_bindings(root / "nd" / "bindings.csv", merged_bindings)
    systems_root.mkdir(parents=True, exist_ok=True)
    for target, content in system_files:
        target.write_text(content, encoding="utf-8")
    return {
        "compositions": len(merged_compositions),
        "assignments": len(merged_assignments),
        "bindings": len(merged_bindings),
        "systems": len(incoming_systems),
    }
