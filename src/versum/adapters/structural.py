"""Safe structural fallback for arbitrary parsed grammars and schema-shaped values."""
from __future__ import annotations

import hashlib
from typing import Any

from .intermediate import GraphProjection, ProjectedNode, ProjectedRelation, SystemIdentity


def _stable_id(prefix: str, path: tuple[str, ...]) -> str:
    digest = hashlib.sha256("/".join(path).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def project_structure(value: Any, identity: SystemIdentity, *, root_label: str = "root") -> GraphProjection:
    """Project nested mappings/sequences without guessing domain semantics.

    All relations are structural containment. Scalar values remain node attributes; no
    causal, intentional, temporal, or contextual meaning is inferred.
    """
    result = GraphProjection(identity=identity)

    def visit(current: Any, path: tuple[str, ...], label: str) -> str:
        node_id = _stable_id(identity.system_id, path)
        if isinstance(current, dict):
            attributes = {str(k): v for k, v in current.items()
                          if not isinstance(v, (dict, list, tuple))}
            node_type = "mapping"
        elif isinstance(current, (list, tuple)):
            attributes = {"length": len(current)}
            node_type = "sequence"
        else:
            attributes = {"value": current}
            node_type = "scalar"
        result.nodes.append(ProjectedNode(node_id, node_type, label, attributes))
        children = current.items() if isinstance(current, dict) else enumerate(current) \
            if isinstance(current, (list, tuple)) else ()
        for key, child in children:
            if not isinstance(child, (dict, list, tuple)):
                continue
            child_path = (*path, str(key))
            child_id = visit(child, child_path, str(key))
            relation_id = _stable_id("relation", (*child_path, "contains"))
            result.relations.append(ProjectedRelation(
                relation_id, node_id, child_id, "contains", "structural", "child",
            ))
        return node_id

    visit(value, (root_label,), root_label)
    return result.validate()
