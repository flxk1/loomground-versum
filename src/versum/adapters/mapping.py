"""Declarative mappings from system-local relations to Federation-5D."""
from __future__ import annotations

from dataclasses import dataclass

from versum.dimensions import Dimension


@dataclass(frozen=True)
class RelationMapping:
    local_predicate: str
    dimension: str
    semantic_role: str = ""

    def validate(self) -> "RelationMapping":
        if not self.local_predicate:
            raise ValueError("relation mapping requires a local predicate")
        Dimension(self.dimension)
        return self


@dataclass(frozen=True)
class SemanticMapping:
    mapping_id: str
    version: str
    relations: dict[str, RelationMapping]

    @classmethod
    def from_dict(cls, raw: dict) -> "SemanticMapping":
        relations = {
            str(name): RelationMapping(
                local_predicate=str(name),
                dimension=str(value["dimension"]),
                semantic_role=str(value.get("semantic_role", "")),
            ).validate()
            for name, value in (raw.get("relations") or {}).items()
        }
        result = cls(str(raw.get("id", "")), str(raw.get("version", "")), relations)
        if not result.mapping_id or not result.version:
            raise ValueError("semantic mapping requires id and version")
        return result

    def relation(self, predicate: str) -> RelationMapping:
        try:
            return self.relations[predicate]
        except KeyError as exc:
            raise ValueError(f"no Federation-5D mapping for relation {predicate!r}") from exc
