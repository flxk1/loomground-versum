"""Reference semantic adapter from Loomground into Graph-Versum."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from versum.adapters import (
    AdapterCapabilities, ArtifactBundle, ExportResult, GraphProjection, ProjectedNode,
    ProjectedRelation, SemanticMapping, SystemIdentity,
)
from versum.nd import Binding, CoordinateAssignment, NDSystem
from versum.loomground import _kit, language_info


ADAPTER_ID = "versum.adapter.loomground"
ADAPTER_VERSION = "1"

LOOMGROUND_MAPPING = SemanticMapping.from_dict({
    "id": "loomground-federation-5d",
    "version": "1",
    "relations": {
        "authority": {"dimension": "intentional", "semantic_role": "authorizes"},
        "pipe": {"dimension": "causal", "semantic_role": "activates"},
        "egress": {"dimension": "causal", "semantic_role": "releases_to"},
        "on_behalf_of": {"dimension": "relational", "semantic_role": "delegates_for"},
        "reservation": {"dimension": "intentional", "semantic_role": "reserves_for"},
        "redress": {"dimension": "intentional", "semantic_role": "remedy_by"},
    },
})


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _id(prefix: str, *parts: Any) -> str:
    return f"{prefix}:{_digest(parts)[:16]}"


def _ordered_relations(axis: str, values: list[str]) -> list[dict]:
    """Materialize transitive precedes pairs because nD relations are attestation-based."""
    return [
        {"axis": axis, "left": left, "right": right, "relation": "precedes"}
        for index, left in enumerate(values) for right in values[index + 1:]
    ]


class LoomgroundAdapter:
    """Adapt authoritative Loomground artifacts and runtime projections to Versum."""

    def __init__(self, implementation: Any = None, *, language_source=None,
                 policy: dict | None = None) -> None:
        self.implementation = implementation
        self.language_source = language_source
        self.policy = dict(policy or {})

    def _kit(self):
        return _kit(self.language_source)

    def identity(self) -> SystemIdentity:
        info = language_info(self.language_source)
        return SystemIdentity(
            system_id="loomground-governance",
            version=info["language_version"],
            grammar_sha256=info["grammar_sha256"],
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
        )

    def capabilities(self) -> AdapterCapabilities:
        runtime = self.implementation is not None
        return AdapterCapabilities(
            artifacts=True,
            structural_projection=True,
            semantic_projection=True,
            parsing=runtime,
            export=True,
            runtime_observations=True,
        )

    def artifacts(self) -> ArtifactBundle:
        kit = self._kit()
        vocabulary_names = (
            "cords", "declarations", "grades", "guard-domain", "node-classes",
            "risk", "verdicts",
        )
        schema_names = ("observation", "patch", "token", "transport")
        return ArtifactBundle(
            grammar=kit.grammar(),
            schemas={name: kit.schema(name) for name in schema_names},
            vocabularies={name: kit.vocabulary(name) for name in vocabulary_names},
            metadata={"language_card": kit.language_card(),
                      "mapping_id": LOOMGROUND_MAPPING.mapping_id,
                      "mapping_version": LOOMGROUND_MAPPING.version},
        )

    def nd_systems(self) -> tuple[NDSystem, ...]:
        artifacts = self.artifacts()
        default_risk = list(artifacts.vocabularies["risk"]["levels"])
        default_grades = list(artifacts.vocabularies["grades"]["levels"])
        risk = list(self.policy.get("risk_levels", default_risk))
        grades = list(self.policy.get("grade_levels", default_grades))
        version_seed = {
            "language": self.identity().version,
            "grammar": self.identity().grammar_sha256,
            "mapping": LOOMGROUND_MAPPING.version,
            "risk": risk,
            "grades": grades,
        }
        raw = {
            "id": "loomground-governance",
            "namespace": "loomground",
            "version": f"{self.identity().version}+{_digest(version_seed)[:12]}",
            "federation_5d_version": "1",
            "axes": {
                "node_class": {"value_type": "controlled_identifier", "cardinality": "one",
                               "vocabulary": ["actor", "human", "gate", "master"]},
                "cord_type": {"value_type": "controlled_identifier", "cardinality": "one",
                              "vocabulary": ["authority", "pipe", "egress"]},
                "risk": {"value_type": "controlled_identifier", "cardinality": "one",
                         "vocabulary": risk, "primitives": ["equal", "precedes"]},
                "grade": {"value_type": "controlled_identifier", "cardinality": "one",
                          "vocabulary": grades, "primitives": ["equal", "precedes"]},
                "party": {"value_type": "entity_reference", "cardinality": "one",
                          "vocabulary_mode": "open", "primitives": ["equal"]},
                "token_kind": {"value_type": "concept_reference", "vocabulary_mode": "open",
                               "primitives": ["equal", "contains"]},
                "tags": {"value_type": "concept_reference", "cardinality": "many",
                         "vocabulary_mode": "open", "primitives": ["equal", "contains"]},
                "verdict": {"value_type": "controlled_identifier", "cardinality": "one",
                            "vocabulary": artifacts.vocabularies["verdicts"]["alphabet"]},
                "reservation_role": {"value_type": "entity_reference", "cardinality": "many",
                                     "vocabulary_mode": "open"},
                "duration": {"value_type": "interval", "cardinality": "one",
                             "vocabulary_mode": "open", "primitives": ["equal", "precedes"]},
                "on_elapse": {"value_type": "controlled_identifier", "cardinality": "one",
                              "vocabulary": ["halt", "proceed"]},
                "redress_role": {"value_type": "entity_reference", "cardinality": "many",
                                 "vocabulary_mode": "open"},
            },
            "bindings": [
                {"form_slot": "predicate.agent", "allowed_axes": ["party", "node_class"]},
                {"form_slot": "predicate.patient", "allowed_axes": ["party", "token_kind"]},
                {"form_slot": "modality.bearer", "allowed_axes": ["party", "reservation_role",
                                                                    "redress_role"]},
                {"form_slot": "condition.antecedent", "allowed_axes": ["risk", "grade",
                                                                         "token_kind", "tags"]},
            ],
            "ontology_relations": [
                *_ordered_relations("risk", risk), *_ordered_relations("grade", grades),
            ],
            "validation": {"unknown_values": "reject", "missing_coordinates": "preserve_unknown",
                           "provenance_required": True},
        }
        return (NDSystem.from_dict(raw).validate(),)

    def parse(self, source: str) -> Any:
        if self.implementation is None:
            raise NotImplementedError("parsing requires a conforming Loomground implementation")
        return self.implementation.parse(source)

    def validate_program(self, program: Any) -> dict:
        if self.implementation is None:
            raise NotImplementedError("validation requires a conforming Loomground implementation")
        return self.implementation.validate(program)

    def project(self, program: Any) -> GraphProjection:
        if self.implementation is None:
            raise NotImplementedError("projection requires a conforming Loomground implementation")
        return self.import_observation(self.implementation.project(program))

    def _assignment(self, system: NDSystem, subject_id: str, axis: str, value: Any,
                    source_ref: str) -> CoordinateAssignment:
        return CoordinateAssignment(
            assignment_id=_id("nda", subject_id, axis, value),
            subject_id=subject_id,
            system_id=system.system_id,
            system_version=system.version,
            axis_id=axis,
            value=value,
            source_id=source_ref,
            method=f"{ADAPTER_ID}@{ADAPTER_VERSION}",
            verification="attested",
        )

    def import_observation(self, value: dict, *, claim_bindings=()) -> GraphProjection:
        required = ("nodes", "cords", "reservations")
        if any(not isinstance(value.get(field), list) for field in required):
            raise ValueError("Loomground observation requires nodes, cords, and reservations lists")
        identity = self.identity()
        system = self.nd_systems()[0]
        source_ref = f"urn:loomground:grammar:{identity.grammar_sha256}"
        result = GraphProjection(identity=identity, nd_systems=[system])
        known: set[str] = set()

        def ensure_node(node_id: str, node_type: str = "external-reference",
                        label: str = "", attributes: dict | None = None) -> str:
            if node_id not in known:
                result.nodes.append(ProjectedNode(node_id, node_type, label or node_id,
                                                  dict(attributes or {}), source_ref))
                known.add(node_id)
            return node_id

        for raw in value["nodes"]:
            node_id = str(raw.get("id", ""))
            node_class = str(raw.get("class", ""))
            if not node_id or not node_class:
                raise ValueError("Loomground observation node requires id and class")
            ensure_node(node_id, node_class, str(raw.get("name") or raw.get("role") or node_id), raw)
            result.assignments.append(self._assignment(system, node_id, "node_class",
                                                       node_class, source_ref))
            for field, axis in (("risk_floor", "risk"), ("grade", "grade"),
                                ("grade_required", "grade"), ("party", "party")):
                if raw.get(field) not in (None, ""):
                    result.assignments.append(self._assignment(
                        system, node_id, axis, raw[field], source_ref))
            delegator = raw.get("on_behalf_of")
            if delegator:
                ensure_node(str(delegator))
                mapping = LOOMGROUND_MAPPING.relation("on_behalf_of")
                result.relations.append(ProjectedRelation(
                    _id("rel", node_id, "on_behalf_of", delegator), node_id, str(delegator),
                    mapping.local_predicate, mapping.dimension, mapping.semantic_role,
                    source_ref=source_ref,
                ))

        for raw in value["cords"]:
            source = ensure_node(str(raw.get("from", "")))
            target = ensure_node(str(raw.get("to", "")))
            predicate = str(raw.get("type", ""))
            mapping = LOOMGROUND_MAPPING.relation(predicate)
            relation_id = _id("rel", source, predicate, target)
            result.relations.append(ProjectedRelation(
                relation_id, source, target, predicate, mapping.dimension,
                mapping.semantic_role, dict(raw), source_ref,
            ))
            result.assignments.append(self._assignment(
                system, relation_id, "cord_type", predicate, source_ref))

        for raw in value["reservations"]:
            constraint_id = _id("reservation", raw)
            role_id = ensure_node(f"role:{raw['by']}", "role", str(raw["by"]))
            ensure_node(constraint_id, "reservation", str(raw.get("kind", "reservation")), raw)
            mapping = LOOMGROUND_MAPPING.relation("reservation")
            result.relations.append(ProjectedRelation(
                _id("rel", constraint_id, "reservation", role_id), constraint_id, role_id,
                mapping.local_predicate, mapping.dimension, mapping.semantic_role,
                dict(raw), source_ref,
            ))
            for field, axis in (("kind", "token_kind"), ("by", "reservation_role"),
                                ("duration", "duration"), ("on_elapse", "on_elapse")):
                if raw.get(field) not in (None, ""):
                    result.assignments.append(self._assignment(
                        system, constraint_id, axis, raw[field], source_ref))

        for raw in value.get("redress", []):
            constraint_id = _id("redress", raw)
            role_id = ensure_node(f"role:{raw['by']}", "role", str(raw["by"]))
            ensure_node(constraint_id, "redress", str(raw.get("kind", "redress")), raw)
            mapping = LOOMGROUND_MAPPING.relation("redress")
            result.relations.append(ProjectedRelation(
                _id("rel", constraint_id, "redress", role_id), constraint_id, role_id,
                mapping.local_predicate, mapping.dimension, mapping.semantic_role,
                dict(raw), source_ref,
            ))
            result.assignments.append(self._assignment(
                system, constraint_id, "redress_role", raw["by"], source_ref))
            if raw.get("within"):
                result.assignments.append(self._assignment(
                    system, constraint_id, "duration", raw["within"], source_ref))

        assignments = {(a.subject_id, a.axis_id): a for a in result.assignments}
        for raw in claim_bindings:
            assignment = assignments.get((str(raw["subject_id"]), str(raw["axis_id"])))
            if assignment is None:
                raise ValueError(f"claim binding has no matching assignment: {raw!r}")
            result.bindings.append(Binding(
                claim_id=str(raw["claim_id"]), form_slot=str(raw["form_slot"]),
                semantic_role=str(raw.get("semantic_role", "")),
                assignment_id=assignment.assignment_id, axis_id=assignment.axis_id,
                value=assignment.value, source_id=source_ref,
                method=f"{ADAPTER_ID}@{ADAPTER_VERSION}", verification="attested",
                binding_id=_id("ndb", raw["claim_id"], assignment.assignment_id,
                               raw["form_slot"]),
            ))
        return result.validate()

    def export(self, projection: GraphProjection) -> ExportResult:
        """Export the graph-shaped Loomground subset; preserve warnings for omitted constraints."""
        lines: list[str] = []
        warnings: list[str] = []
        for node in projection.nodes:
            attrs = node.attributes
            if node.node_type == "actor":
                suffix = ""
                for key, token in (("party", "party"), ("on_behalf_of", "on-behalf-of"),
                                   ("grade", "grade")):
                    if attrs.get(key):
                        suffix += f" {token} {attrs[key]}"
                lines.append(f"actor {node.node_id}{suffix}")
            elif node.node_type == "human":
                suffix = f" role {attrs['role']}" if attrs.get("role") else ""
                lines.append(f"human {node.node_id}{suffix}")
            elif node.node_type == "gate":
                suffix = ""
                for key, token in (("risk_floor", "risk"), ("grade_required", "grade"),
                                   ("party", "party")):
                    if attrs.get(key):
                        suffix += f" {token} {attrs[key]}"
                lines.append(f"gate {node.node_id}{suffix}")
            elif node.node_type in {"reservation", "redress", "role", "master",
                                    "external-reference"}:
                continue
            else:
                warnings.append(f"node {node.node_id!r} has no Loomground export mapping")
        for relation in projection.relations:
            if relation.local_predicate in {"authority", "pipe", "egress"}:
                lines.append(f"cord {relation.source_id} -> {relation.target_id}")
            elif relation.local_predicate not in {"on_behalf_of", "reservation", "redress"}:
                warnings.append(f"relation {relation.relation_id!r} was not exported")
        return ExportResult("text/x-loomground", "\n".join(lines) + ("\n" if lines else ""),
                            tuple(warnings))
