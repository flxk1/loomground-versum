"""Typed, versioned and user-extensible nD contextual coordinate systems.

Configuration is declarative. JSON is supported by the standard library; YAML is accepted
when PyYAML is installed. Configurations cannot contain executable hooks. Optional adapters
are references only and must be supplied explicitly by a host application.
"""
from __future__ import annotations

import json
import csv
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

from .loomground import language_info


class VocabularyMode(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    EXTERNAL = "external"


class Primitive(str, Enum):
    EQUAL = "equal"
    CONTAINS = "contains"
    CONTAINED_BY = "contained_by"
    OVERLAPS = "overlaps"
    DISJOINT = "disjoint"
    PRECEDES = "precedes"
    SUCCEEDS = "succeeds"


class Truth(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")
_VALUE_TYPES = frozenset({
    "string", "controlled_identifier", "concept_reference", "entity_reference",
    "integer", "non_negative_integer", "number", "boolean", "date", "interval",
    "quantity",
})


def _tuple(value) -> tuple:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(value)
    return (value,)


@dataclass(frozen=True)
class AxisSpec:
    axis_id: str
    value_type: str
    cardinality: str = "many"
    vocabulary_mode: str = "open"
    vocabulary: tuple = ()
    primitives: tuple = (Primitive.EQUAL.value,)
    ontology_id: str = ""
    ontology_version: str = ""
    provenance_required: bool = True
    unit: str = ""
    value_range: tuple = ()

    @classmethod
    def from_dict(cls, axis_id: str, raw: dict) -> "AxisSpec":
        ontology = raw.get("ontology") or {}
        return cls(
            axis_id=axis_id,
            value_type=str(raw.get("value_type", "string")),
            cardinality=str(raw.get("cardinality", "many")),
            vocabulary_mode=str(raw.get("vocabulary_mode", "closed"
                                       if "vocabulary" in raw else "open")),
            vocabulary=_tuple(raw.get("vocabulary")),
            primitives=tuple(str(x) for x in _tuple(
                raw.get("primitives", (Primitive.EQUAL.value,)))),
            ontology_id=str(raw.get("ontology_id") or ontology.get("id") or ""),
            ontology_version=str(raw.get("ontology_version") or
                                 ontology.get("version") or ""),
            provenance_required=bool(raw.get("provenance_required", True)),
            unit=str(raw.get("unit", "")),
            value_range=_tuple(raw.get("range")),
        )

    def violations(self) -> list[str]:
        out = []
        if not _ID_RE.match(self.axis_id):
            out.append(f"invalid axis_id {self.axis_id!r}")
        if self.value_type not in _VALUE_TYPES:
            out.append(f"axis {self.axis_id}: unknown value_type {self.value_type!r}")
        if self.cardinality not in {"one", "many"}:
            out.append(f"axis {self.axis_id}: cardinality must be 'one' or 'many'")
        try:
            mode = VocabularyMode(self.vocabulary_mode)
        except ValueError:
            out.append(f"axis {self.axis_id}: unknown vocabulary_mode {self.vocabulary_mode!r}")
            mode = None
        if mode == VocabularyMode.CLOSED and not self.vocabulary:
            out.append(f"axis {self.axis_id}: closed vocabulary is empty")
        if mode == VocabularyMode.EXTERNAL and not (self.ontology_id and self.ontology_version):
            out.append(f"axis {self.axis_id}: external ontology requires id and version")
        for rel in self.primitives:
            try:
                Primitive(rel)
            except ValueError:
                out.append(f"axis {self.axis_id}: unknown primitive {rel!r}")
        return out

    def validate_value(self, value: Any) -> list[str]:
        out = []
        if self.vocabulary_mode == VocabularyMode.CLOSED.value and value not in self.vocabulary:
            out.append(f"axis {self.axis_id}: value {value!r} is outside the closed vocabulary")
        if self.value_type in {"integer", "non_negative_integer"} and (
                not isinstance(value, int) or isinstance(value, bool)):
            out.append(f"axis {self.axis_id}: value {value!r} is not an integer")
        if self.value_type == "non_negative_integer" and isinstance(value, int) and value < 0:
            out.append(f"axis {self.axis_id}: value must be non-negative")
        if self.value_type == "number" and (
                not isinstance(value, (int, float)) or isinstance(value, bool)):
            out.append(f"axis {self.axis_id}: value {value!r} is not numeric")
        if self.value_type == "boolean" and not isinstance(value, bool):
            out.append(f"axis {self.axis_id}: value {value!r} is not boolean")
        if self.value_type == "quantity":
            if not isinstance(value, dict) or "amount" not in value:
                out.append(f"axis {self.axis_id}: quantity requires an amount")
            elif self.unit and value.get("unit") != self.unit:
                out.append(f"axis {self.axis_id}: quantity unit must be {self.unit!r}")
            elif self.value_range and not (
                    self.value_range[0] <= value["amount"] <= self.value_range[-1]):
                out.append(f"axis {self.axis_id}: quantity is outside range {self.value_range}")
        return out


@dataclass(frozen=True)
class BindingRule:
    form_slot: str
    allowed_axes: tuple
    required: bool = False

    @classmethod
    def from_dict(cls, raw: dict) -> "BindingRule":
        return cls(str(raw.get("form_slot", "")), _tuple(raw.get("allowed_axes")),
                   bool(raw.get("required", False)))


@dataclass(frozen=True)
class NDSystem:
    system_id: str
    namespace: str
    version: str
    federation_5d_version: str
    axes: dict[str, AxisSpec]
    bindings: tuple[BindingRule, ...] = ()
    ontology_relations: tuple[dict, ...] = ()
    unknown_values: str = "reject"
    missing_coordinates: str = "preserve_unknown"
    provenance_required: bool = True

    @classmethod
    def from_dict(cls, raw: dict) -> "NDSystem":
        root = raw.get("nd_system", raw)
        axes = {str(k): AxisSpec.from_dict(str(k), v or {})
                for k, v in (root.get("axes") or {}).items()}
        validation = root.get("validation") or {}
        return cls(
            system_id=str(root.get("id", "")),
            namespace=str(root.get("namespace", "")),
            version=str(root.get("version", "")),
            federation_5d_version=str(root.get("federation_5d_version", "1")),
            axes=axes,
            bindings=tuple(BindingRule.from_dict(x) for x in root.get("bindings", ())),
            ontology_relations=tuple(root.get("ontology_relations", ())),
            unknown_values=str(validation.get("unknown_values", "reject")),
            missing_coordinates=str(validation.get(
                "missing_coordinates", "preserve_unknown")),
            provenance_required=bool(validation.get("provenance_required", True)),
        )

    def violations(self) -> list[str]:
        out = []
        for label, value in (("id", self.system_id), ("namespace", self.namespace),
                             ("version", self.version)):
            if not value or (label != "version" and not _ID_RE.match(value)):
                out.append(f"invalid or missing nD system {label}: {value!r}")
        if not self.axes:
            out.append("nD system must declare at least one axis")
        for axis in self.axes.values():
            out.extend(axis.violations())
        for binding in self.bindings:
            if not binding.form_slot:
                out.append("binding rule has no form_slot")
            for axis_id in binding.allowed_axes:
                if axis_id not in self.axes:
                    out.append(f"binding {binding.form_slot}: unknown axis {axis_id!r}")
        return out

    def validate(self) -> "NDSystem":
        errors = self.violations()
        if errors:
            raise ValueError("invalid nD system: " + "; ".join(errors))
        return self

    def qualified_axis(self, axis_id: str) -> str:
        if axis_id not in self.axes:
            raise KeyError(axis_id)
        return f"{self.namespace}:{axis_id}"

    def relation(self, axis_id: str, left: Any, right: Any,
                 primitive: Primitive | str) -> Truth:
        """Evaluate an attested primitive relation; absence remains unknown."""
        axis = self.axes[axis_id]
        rel = Primitive(primitive)
        inverse = {
            Primitive.CONTAINS: Primitive.CONTAINED_BY,
            Primitive.CONTAINED_BY: Primitive.CONTAINS,
            Primitive.PRECEDES: Primitive.SUCCEEDS,
            Primitive.SUCCEEDS: Primitive.PRECEDES,
        }.get(rel)
        # Directional primitives imply support for their inverse query.
        if rel.value not in axis.primitives and not (
                inverse and inverse.value in axis.primitives):
            return Truth.UNKNOWN
        if rel == Primitive.EQUAL:
            return Truth.TRUE if left == right else Truth.FALSE
        for row in self.ontology_relations:
            if (row.get("axis") == axis_id and row.get("left") == left and
                    row.get("right") == right and row.get("relation") == rel.value):
                return Truth.TRUE
        if inverse:
            for row in self.ontology_relations:
                if (row.get("axis") == axis_id and row.get("left") == right and
                        row.get("right") == left and row.get("relation") == inverse.value):
                    return Truth.TRUE
        return Truth.UNKNOWN


_CORE_SYSTEM = {
    "id": "versum-context",
    "namespace": "versum.context",
    "version": "1",
    "federation_5d_version": "1",
    "axes": {
        "jurisdiction": {"value_type": "controlled_identifier", "vocabulary_mode": "open",
                         "primitives": ["equal", "contains", "overlaps", "disjoint"]},
        "time": {"value_type": "interval", "vocabulary_mode": "open",
                 "primitives": ["equal", "contains", "overlaps", "disjoint", "precedes"]},
        "instrument": {"value_type": "controlled_identifier", "vocabulary_mode": "open",
                       "primitives": ["equal"]},
        "domain": {"value_type": "concept_reference", "vocabulary_mode": "open",
                   "primitives": ["equal", "contains", "overlaps"]},
        "language": {"value_type": "controlled_identifier", "vocabulary_mode": "open",
                     "primitives": ["equal"]},
        "version": {"value_type": "controlled_identifier", "vocabulary_mode": "open",
                    "primitives": ["equal", "precedes"]},
        "actor": {"value_type": "concept_reference", "vocabulary_mode": "open",
                  "primitives": ["equal", "contains"]},
        "fact_scope": {"value_type": "concept_reference", "vocabulary_mode": "open",
                       "primitives": ["equal", "contains", "overlaps", "disjoint"]},
        "scenario": {"value_type": "concept_reference", "vocabulary_mode": "open",
                     "primitives": ["equal"]},
        "purpose": {"value_type": "concept_reference", "vocabulary_mode": "open",
                    "primitives": ["equal", "contains", "overlaps"]},
    },
    "bindings": [
        {"form_slot": "quantification.range", "allowed_axes": ["actor", "fact_scope"]},
        {"form_slot": "predicate.agent", "allowed_axes": ["actor"]},
        {"form_slot": "predicate.patient", "allowed_axes": ["actor", "fact_scope"]},
        {"form_slot": "modality.bearer", "allowed_axes": ["actor"]},
        {"form_slot": "condition.antecedent", "allowed_axes": ["fact_scope"]},
    ],
}


def core_system() -> NDSystem:
    """The domain-neutral contextual axes Versum understands without a user package."""
    return NDSystem.from_dict(_CORE_SYSTEM).validate()


@dataclass(frozen=True)
class CoordinateAssignment:
    subject_id: str
    system_id: str
    system_version: str
    axis_id: str
    value: Any
    source_id: str
    method: str
    confidence: str = ""
    verification: str = "candidate"
    assignment_id: str = ""

    def violations(self, system: NDSystem) -> list[str]:
        out = []
        if self.system_id != system.system_id or self.system_version != system.version:
            out.append("coordinate assignment nD system id/version mismatch")
        axis = system.axes.get(self.axis_id)
        if not axis:
            out.append(f"unknown nD axis {self.axis_id!r}")
            return out
        if (system.provenance_required or axis.provenance_required) and not self.source_id:
            out.append(f"axis {self.axis_id}: coordinate provenance is required")
        if not self.method:
            out.append(f"axis {self.axis_id}: assignment method is required")
        out.extend(axis.validate_value(self.value))
        return out


@dataclass(frozen=True)
class Binding:
    claim_id: str
    form_slot: str
    semantic_role: str
    assignment_id: str
    axis_id: str
    value: Any
    source_id: str
    method: str
    confidence: str = ""
    verification: str = "candidate"
    binding_id: str = ""

    def violations(self, system: NDSystem) -> list[str]:
        out = []
        rules = [r for r in system.bindings if r.form_slot == self.form_slot]
        if not rules:
            out.append(f"form slot {self.form_slot!r} has no binding contract")
        elif not any(self.axis_id in r.allowed_axes for r in rules):
            out.append(f"axis {self.axis_id!r} is not allowed for slot {self.form_slot!r}")
        if not self.claim_id or not self.assignment_id:
            out.append("binding requires claim_id and assignment_id")
        if not self.source_id or not self.method:
            out.append("binding requires provenance source_id and method")
        return out


def load_system(path) -> NDSystem:
    """Load and validate a declarative JSON or YAML nD system configuration."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        raw = json.loads(text)
    elif p.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - depends on optional package
            raise RuntimeError("YAML nD configs require the optional PyYAML package") from exc
        raw = yaml.safe_load(text)
    else:
        raise ValueError("nD system config must be .json, .yaml, or .yml")
    if not isinstance(raw, dict):
        raise ValueError("nD system config root must be an object")
    return NDSystem.from_dict(raw).validate()


class NDRegistry:
    """A collision-safe collection of independently versioned nD systems."""

    def __init__(self, include_core: bool = False):
        self.systems: dict[tuple[str, str], NDSystem] = {}
        self.axes: dict[str, tuple[str, str]] = {}
        if include_core:
            self.register(core_system())

    def register(self, system: NDSystem) -> NDSystem:
        system.validate()
        key = (system.system_id, system.version)
        previous = self.systems.get(key)
        if previous is not None and previous != system:
            raise ValueError(f"different nD systems claim id/version {key!r}")
        for axis_id in system.axes:
            qualified = system.qualified_axis(axis_id)
            owner = self.axes.get(qualified)
            if owner is not None and owner != key:
                raise ValueError(f"nD axis collision on {qualified!r}: {owner!r} vs {key!r}")
            self.axes[qualified] = key
        self.systems[key] = system
        return system

    def load(self, paths) -> "NDRegistry":
        for path in paths:
            self.register(load_system(path))
        return self

    def manifest(self) -> dict:
        return {
            "grammar": language_info(),
            "systems": [
                {"id": s.system_id, "namespace": s.namespace, "version": s.version,
                 "federation_5d_version": s.federation_5d_version,
                 "axes": sorted(s.qualified_axis(a) for a in s.axes)}
                for s in sorted(self.systems.values(),
                                key=lambda x: (x.system_id, x.version))
            ]
        }


ASSIGNMENT_COLUMNS = (
    "assignment_id", "subject_id", "system_id", "system_version", "axis_id", "value",
    "source_id", "method", "confidence", "verification")
BINDING_COLUMNS = (
    "binding_id", "claim_id", "form_slot", "semantic_role", "assignment_id", "axis_id",
    "value", "source_id", "method", "confidence", "verification")


def _save_rows(path, columns, rows) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            data = asdict(cast(Any, row)) if is_dataclass(row) and not isinstance(row, type) \
                else dict(row)
            data["value"] = json.dumps(data.get("value"), ensure_ascii=False, sort_keys=True)
            w.writerow(data)


def _load_rows(path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        try:
            row["value"] = json.loads(row.get("value", "null"))
        except json.JSONDecodeError:
            row["value"] = row.get("value")
    return rows


def save_assignments(path, rows) -> None:
    """Persist coordinate assignments without flattening typed values to ambiguous text."""
    _save_rows(path, ASSIGNMENT_COLUMNS, rows)


def load_assignments(path) -> list[dict]:
    return _load_rows(path)


def save_bindings(path, rows) -> None:
    _save_rows(path, BINDING_COLUMNS, rows)


def load_bindings(path) -> list[dict]:
    return _load_rows(path)


def required_binding_gaps(claim_ids, system: NDSystem, bindings) -> list[dict]:
    """Report required form-slot bindings that are absent; never invalidate provenance."""
    bound = {(b.claim_id if isinstance(b, Binding) else b.get("claim_id"),
              b.form_slot if isinstance(b, Binding) else b.get("form_slot"))
             for b in bindings}
    out = []
    for claim_id in claim_ids:
        for rule in system.bindings:
            if rule.required and (claim_id, rule.form_slot) not in bound:
                out.append({"claim_id": claim_id, "form_slot": rule.form_slot,
                            "diagnostic": "contextually-incomplete",
                            "allowed_axes": list(rule.allowed_axes)})
    return out


def scope_compatibility(system: NDSystem, left: dict[str, list],
                        right: dict[str, list]) -> dict:
    """Derived compatibility diagnostic with primitive evidence.

    ``left`` and ``right`` map axis ids to values. A proven disjoint pair makes the scopes
    incompatible. Compatibility is true only when every shared axis has an attested positive
    relation; missing ontology knowledge remains unknown.
    """
    evidence = []
    any_unknown = False
    shared = sorted(set(left) & set(right))
    if not shared:
        return {"result": Truth.UNKNOWN.value, "evidence": [],
                "reason": "no-shared-defined-axis"}
    positive = (Primitive.EQUAL, Primitive.OVERLAPS,
                Primitive.CONTAINS, Primitive.CONTAINED_BY)
    for axis_id in shared:
        matched = False
        axis_unknown = False
        for lv in _tuple(left[axis_id]):
            for rv in _tuple(right[axis_id]):
                disjoint = system.relation(axis_id, lv, rv, Primitive.DISJOINT)
                evidence.append({"axis": axis_id, "left": lv, "right": rv,
                                 "primitive": Primitive.DISJOINT.value,
                                 "result": disjoint.value})
                if disjoint == Truth.TRUE:
                    return {"result": Truth.FALSE.value, "evidence": evidence,
                            "reason": "attested-disjoint"}
                for rel in positive:
                    result = system.relation(axis_id, lv, rv, rel)
                    if result == Truth.TRUE:
                        evidence.append({"axis": axis_id, "left": lv, "right": rv,
                                         "primitive": rel.value, "result": result.value})
                        matched = True
                        break
                if not matched:
                    axis_unknown = True
        if axis_unknown and not matched:
            any_unknown = True
    return {"result": Truth.UNKNOWN.value if any_unknown else Truth.TRUE.value,
            "evidence": evidence,
            "reason": "primitive-knowledge-incomplete" if any_unknown else "all-shared-compatible"}


def select_by_scope(system: NDSystem, claim_scopes: dict[str, dict],
                    constraint: dict) -> dict:
    """Partition claims by contextual compatibility without resolving their content."""
    selected, excluded, unknown, diagnostics = [], [], [], {}
    for claim_id, scope in sorted(claim_scopes.items()):
        diagnostic = scope_compatibility(system, scope, constraint)
        diagnostics[claim_id] = diagnostic
        if diagnostic["result"] == Truth.TRUE.value:
            selected.append(claim_id)
        elif diagnostic["result"] == Truth.FALSE.value:
            excluded.append(claim_id)
        else:
            unknown.append(claim_id)
    return {"selected": selected, "excluded": excluded, "unknown": unknown,
            "diagnostics": diagnostics}
