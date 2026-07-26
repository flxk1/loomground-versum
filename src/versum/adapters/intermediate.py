"""Neutral interchange types produced by language and system adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from versum.nd import Binding, CoordinateAssignment, NDSystem


@dataclass(frozen=True)
class SystemIdentity:
    system_id: str
    version: str
    grammar_sha256: str
    adapter_id: str
    adapter_version: str


@dataclass(frozen=True)
class AdapterCapabilities:
    artifacts: bool = True
    structural_projection: bool = False
    semantic_projection: bool = False
    parsing: bool = False
    export: bool = False
    runtime_observations: bool = False


@dataclass(frozen=True)
class ArtifactBundle:
    grammar: str
    schemas: dict[str, Any] = field(default_factory=dict)
    vocabularies: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectedNode:
    node_id: str
    node_type: str
    label: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    source_ref: str = ""


@dataclass(frozen=True)
class ProjectedRelation:
    relation_id: str
    source_id: str
    target_id: str
    local_predicate: str
    dimension: str
    semantic_role: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    source_ref: str = ""


@dataclass
class GraphProjection:
    identity: SystemIdentity
    nodes: list[ProjectedNode] = field(default_factory=list)
    relations: list[ProjectedRelation] = field(default_factory=list)
    nd_systems: list[NDSystem] = field(default_factory=list)
    assignments: list[CoordinateAssignment] = field(default_factory=list)
    bindings: list[Binding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def edge_rows(self) -> list[dict]:
        """Render system relations in Versum's typed semantic-edge contract."""
        from versum.store.graph import Edge
        return [Edge(
            edge_id=relation.relation_id,
            src_id=relation.source_id,
            dst_id=relation.target_id,
            edge_type="system_relation",
            rationale=str(relation.attributes),
            verification="attested",
            edge_family="semantic",
            dimension=relation.dimension,
            semantic_role=relation.semantic_role,
            method_version=f"{self.identity.adapter_id}@{self.identity.adapter_version}",
            local_predicate=relation.local_predicate,
            system_id=self.identity.system_id,
            system_version=self.identity.version,
            source_ref=relation.source_ref,
        ).row() for relation in self.relations]

    def violations(self) -> list[str]:
        """Return referential and contract violations without mutating the projection."""
        out: list[str] = []
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            out.append("projection contains duplicate node ids")
        relation_ids = {relation.relation_id for relation in self.relations}
        if len(relation_ids) != len(self.relations):
            out.append("projection contains duplicate relation ids")
        for relation in self.relations:
            if relation.source_id not in node_ids:
                out.append(f"relation {relation.relation_id}: unknown source {relation.source_id!r}")
            if relation.target_id not in node_ids:
                out.append(f"relation {relation.relation_id}: unknown target {relation.target_id!r}")
        systems = {(system.system_id, system.version): system for system in self.nd_systems}
        for assignment in self.assignments:
            system = systems.get((assignment.system_id, assignment.system_version))
            if system is None:
                out.append(f"assignment for unknown system {assignment.system_id!r}")
            else:
                out.extend(assignment.violations(system))
        for binding in self.bindings:
            matching = [system for system in self.nd_systems if binding.axis_id in system.axes]
            if not matching:
                out.append(f"binding for unknown axis {binding.axis_id!r}")
            else:
                out.extend(binding.violations(matching[0]))
        return out

    def validate(self) -> "GraphProjection":
        errors = self.violations()
        if errors:
            raise ValueError("invalid adapter projection: " + "; ".join(errors))
        return self


@dataclass(frozen=True)
class ExportResult:
    media_type: str
    content: str
    warnings: tuple[str, ...] = ()
