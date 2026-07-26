"""Declared K3 projections and deterministic rebuild operations."""
from __future__ import annotations

import json
from pathlib import Path

from .events import replay_event_log

PROJECTION_DIR = "_projections"
SEARCH_FILE = "search-index.json"


def projection_contract() -> dict:
    """Return the machine-readable authority/rebuild classification."""
    return {
        "schema": "loomground.versum.projections/v1",
        "projections": {
            "event-materialization": {
                "inputs": ["_events.jsonl"],
                "outputs": ["by-domain/", "_sync_state.json", "_nd_systems.json",
                            "_graph_version.json"],
                "rebuild": "replay-events",
            },
            "coordinate-canon": {
                "inputs": ["by-domain/*/claims.csv"],
                "outputs": ["by-domain/*/concepts.csv", "by-domain/*/semantic_edges.csv",
                            "by-domain/*/composition_edges.csv", "canon.json",
                            "convergence.json"],
                "rebuild": "canon",
            },
            "search": {
                "inputs": ["by-domain/*/claims.csv", "canon.json"],
                "outputs": [f"{PROJECTION_DIR}/{SEARCH_FILE}"],
                "rebuild": "rebuild-projections",
            },
        },
        "protected_inputs": {
            "confirmed-curation": {
                "paths": [".versum/concepts.csv", ".versum/semantic_edges.csv"],
                "reason": "curator confirmation is an authored decision, not a cache",
            }
        },
    }


def rebuild_search_projection(kg_root) -> dict:
    """Rebuild the portable search document snapshot; postings/BM25 rebuild on load."""
    from .store.retrieve import from_kg

    root = Path(kg_root)
    output = root / PROJECTION_DIR / SEARCH_FILE
    index = from_kg(root)
    index.save(output)
    manifest = projection_contract()
    manifest_path = root / PROJECTION_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                        sort_keys=True) + "\n", encoding="utf-8")
    return {"documents": len(index.docs), "output": str(output),
            "manifest": str(manifest_path)}


def rebuild_projections(source_root, target_root, config: dict | None = None,
                        m_max: int = 1) -> dict:
    """Build all deterministic KG projections in an empty target, preserving source data."""
    from .concept.canon import curate_kg

    report = replay_event_log(source_root, target_root)
    cfg = dict(config or {})
    cfg["kg_root"] = str(Path(target_root))
    canon = curate_kg(cfg, m_max=m_max)
    search = rebuild_search_projection(target_root)
    return {**report, "canon": canon, "search": search}
