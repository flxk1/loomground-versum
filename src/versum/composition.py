"""Typed, provenance-grounded composition schemas.

Co-occurrence may propose a composition, but participant roles define its semantics. The
module validates shapes; it does not decide whether a proposed composition is substantively
true.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path


class CompositionKind(str, Enum):
    ENTITY = "entity"
    DEONTIC = "deontic"
    PROCESS = "process"
    CONDITIONAL = "conditional"
    RELATION = "relation"
    TEMPORAL_DIFF = "temporal_diff"
    COMPOSITE = "composite"


_REQUIRED = {
    CompositionKind.ENTITY: {"evidence"},
    CompositionKind.DEONTIC: {"bearer", "action"},
    CompositionKind.PROCESS: {"step"},
    CompositionKind.CONDITIONAL: {"antecedent", "consequent"},
    CompositionKind.RELATION: {"subject", "operator", "object"},
    CompositionKind.TEMPORAL_DIFF: {"before", "after"},
    CompositionKind.COMPOSITE: {"member"},
}


@dataclass(frozen=True)
class Participant:
    role: str
    target_id: str
    evidence_ids: tuple = ()
    position: int | None = None


@dataclass(frozen=True)
class Composition:
    composition_id: str
    kind: str
    participants: tuple[Participant, ...]
    label: str = ""
    verification: str = "candidate"
    method_version: str = ""
    nd_scope: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "composition_id": self.composition_id,
            "kind": self.kind,
            "participants": [
                {"role": participant.role, "target_id": participant.target_id,
                 "evidence_ids": list(participant.evidence_ids),
                 "position": participant.position}
                for participant in self.participants
            ],
            "label": self.label,
            "verification": self.verification,
            "method_version": self.method_version,
            "nd_scope": dict(self.nd_scope),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Composition":
        return cls(
            composition_id=str(raw.get("composition_id", "")),
            kind=str(raw.get("kind", "")),
            participants=tuple(Participant(
                role=str(participant.get("role", "")),
                target_id=str(participant.get("target_id", "")),
                evidence_ids=tuple(participant.get("evidence_ids", ())),
                position=participant.get("position"),
            ) for participant in raw.get("participants", ())),
            label=str(raw.get("label", "")),
            verification=str(raw.get("verification", "candidate")),
            method_version=str(raw.get("method_version", "")),
            nd_scope=dict(raw.get("nd_scope", {})),
        )

    def violations(self) -> list[str]:
        out = []
        try:
            kind = CompositionKind(self.kind)
        except ValueError:
            return [f"unknown composition kind {self.kind!r}"]
        if not self.composition_id:
            out.append("composition_id is required")
        roles = {p.role.split(":", 1)[0] for p in self.participants}
        for role in sorted(_REQUIRED[kind] - roles):
            out.append(f"{kind.value} composition requires role {role!r}")
        for p in self.participants:
            if not p.target_id:
                out.append(f"participant {p.role!r} has no target_id")
            if not p.evidence_ids:
                out.append(f"participant {p.role!r} has no grounding evidence")
        if kind in {CompositionKind.PROCESS, CompositionKind.COMPOSITE}:
            repeat = "step" if kind == CompositionKind.PROCESS else "member"
            if sum(1 for p in self.participants if p.role.split(":", 1)[0] == repeat) < 2:
                out.append(f"{kind.value} composition requires at least two {repeat} participants")
        return out

    def edge_rows(self) -> list[dict]:
        """Project participants to typed structural composition edges."""
        from .store.graph import composition_edge
        rows = []
        for i, p in enumerate(self.participants):
            rows.append(composition_edge(
                f"{self.composition_id}:{i + 1}", p.target_id, self.composition_id,
                role=p.role, evidence_ids=p.evidence_ids,
                verification=self.verification))
            rows[-1]["method_version"] = self.method_version
            rows[-1]["scope"] = json.dumps(self.nd_scope, sort_keys=True)
        return rows


def save_compositions(path, compositions) -> None:
    """Persist validated typed compositions as deterministic JSON Lines."""
    rows = []
    seen = set()
    for raw in compositions:
        composition = raw if isinstance(raw, Composition) else Composition.from_dict(raw)
        errors = composition.violations()
        if errors:
            raise ValueError("invalid composition: " + "; ".join(errors))
        if composition.composition_id in seen:
            raise ValueError(f"duplicate composition id {composition.composition_id!r}")
        seen.add(composition.composition_id)
        rows.append(composition)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(
        json.dumps(row.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
        for row in sorted(rows, key=lambda item: item.composition_id)
    ), encoding="utf-8")


def load_compositions(path) -> list[Composition]:
    """Load and validate typed compositions; absence means no compositions held."""
    source = Path(path)
    if not source.is_file():
        return []
    rows = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            composition = Composition.from_dict(json.loads(line))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid composition record at line {line_number}: {exc}") from exc
        errors = composition.violations()
        if errors:
            raise ValueError(f"invalid composition at line {line_number}: " + "; ".join(errors))
        rows.append(composition)
    if len({row.composition_id for row in rows}) != len(rows):
        raise ValueError("composition store contains duplicate ids")
    return rows
