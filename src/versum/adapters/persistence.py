"""Deterministic persistence for adapter-produced Graph-Versum projections."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from versum.store.graph import save_edges
from versum.nd import save_assignments, save_bindings

from .intermediate import GraphProjection


def save_projection(path, projection: GraphProjection) -> Path:
    """Write a validated projection as a self-contained Graph-Versum adapter layer."""
    projection.validate()
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    (root / "identity.json").write_text(
        json.dumps(asdict(projection.identity), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (root / "nodes.json").write_text(
        json.dumps([asdict(node) for node in projection.nodes], ensure_ascii=False,
                   indent=2, sort_keys=True), encoding="utf-8")
    (root / "systems.json").write_text(
        json.dumps([{
            "id": system.system_id, "namespace": system.namespace,
            "version": system.version,
            "federation_5d_version": system.federation_5d_version,
            "axes": sorted(system.qualified_axis(axis) for axis in system.axes),
        } for system in projection.nd_systems], ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8")
    save_edges(root / "relations.csv", projection.edge_rows())
    save_assignments(root / "assignments.csv", projection.assignments)
    save_bindings(root / "bindings.csv", projection.bindings)
    return root
