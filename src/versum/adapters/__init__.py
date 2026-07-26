"""Universal adapters from external languages and systems into Graph-Versum."""

from .intermediate import (
    AdapterCapabilities, ArtifactBundle, ExportResult, GraphProjection, ProjectedNode,
    ProjectedRelation, SystemIdentity,
)
from .mapping import RelationMapping, SemanticMapping
from .protocol import SystemAdapter
from .persistence import save_projection
from .registry import AdapterRegistry
from .structural import project_structure

__all__ = [
    "AdapterCapabilities", "AdapterRegistry", "ArtifactBundle", "ExportResult",
    "GraphProjection", "ProjectedNode", "ProjectedRelation", "RelationMapping",
    "SemanticMapping", "SystemAdapter", "SystemIdentity", "project_structure",
    "save_projection",
]
