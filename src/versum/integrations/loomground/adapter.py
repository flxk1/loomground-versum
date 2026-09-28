"""Reference semantic adapter from Loomground into Graph-Versum."""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
from typing import Any

from versum.adapters import (
    AdapterCapabilities, ArtifactBundle, ExportResult, GraphProjection, ProjectedNode,
    ProjectedRelation, SemanticMapping, SystemIdentity,
)
from versum.nd import Binding, CoordinateAssignment, NDSystem
from versum.loomground import LoomgroundSourceError, _kit, language_info


ADAPTER_ID = "versum.adapter.loomground"
ADAPTER_VERSION = "1"

def _governance_plane(kit) -> Any:
    """The kit's plane module: the one source of the 5D binding and the nD system."""
    try:
        return importlib.import_module(f"{kit.__name__}.plane")
    except ImportError as exc:
        raise LoomgroundSourceError(
            "the Loomground adoption kit publishes no governance plane "
            "(loomground_governance.plane); install a kit that ships it") from exc


def loomground_mapping(language_source=None) -> SemanticMapping:
    """The governance relation -> 5D mapping, read from the kit's package data at runtime."""
    return SemanticMapping.from_dict(_governance_plane(_kit(language_source))
                                     .dimension_binding())


def __getattr__(name: str) -> Any:
    # ``LOOMGROUND_MAPPING`` stays importable but is resolved from the kit on access, so
    # importing the versum never requires the kit and no copy of the map lives here.
    if name == "LOOMGROUND_MAPPING":
        return loomground_mapping()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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

    def mapping(self) -> SemanticMapping:
        """The relation -> 5D mapping from the kit's governance plane data file."""
        return loomground_mapping(self.language_source)

    def plane(self) -> dict:
        """The kit's governance plane descriptor (shared plane descriptor contract v1)."""
        return _governance_plane(self._kit()).plane()

    def artifacts(self) -> ArtifactBundle:
        kit = self._kit()
        mapping = self.mapping()
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
                      "mapping_id": mapping.mapping_id,
                      "mapping_version": mapping.version},
        )

    def nd_systems(self) -> tuple[NDSystem, ...]:
        """The governance nD system: the plane's own document, with policy ladders applied.

        Axes, vocabularies and slot rules come from the kit's plane at runtime; the policy
        may remap the risk and grade ladders, and the version pins language, grammar,
        mapping and the active ladders so a stale assignment is detectable.
        """
        raw = copy.deepcopy(self.plane()["nd_system"])
        axes = raw["axes"]
        risk = list(self.policy.get("risk_levels", axes["risk"]["vocabulary"]))
        grades = list(self.policy.get("grade_levels", axes["grade"]["vocabulary"]))
        axes["risk"]["vocabulary"], axes["grade"]["vocabulary"] = risk, grades
        identity = self.identity()
        version_seed = {
            "language": identity.version,
            "grammar": identity.grammar_sha256,
            "mapping": self.mapping().version,
            "risk": risk,
            "grades": grades,
        }
        raw["version"] = f"{identity.version}+{_digest(version_seed)[:12]}"
        raw["ontology_relations"] = [
            row for row in raw.get("ontology_relations", [])
            if row.get("axis") not in {"risk", "grade"}
        ] + [*_ordered_relations("risk", risk), *_ordered_relations("grade", grades)]
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
        semantic = self.mapping()

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

        # Delegation edges after every declared node exists, so a delegator declared
        # later in the list keeps its own class and attributes (not a placeholder).
        for raw in value["nodes"]:
            node_id = str(raw["id"])
            delegator = raw.get("on_behalf_of")
            if delegator:
                ensure_node(str(delegator))
                mapping = semantic.relation("on_behalf_of")
                result.relations.append(ProjectedRelation(
                    _id("rel", node_id, "on_behalf_of", delegator), node_id, str(delegator),
                    mapping.local_predicate, mapping.dimension, mapping.semantic_role,
                    source_ref=source_ref,
                ))

        for raw in value["cords"]:
            source = ensure_node(str(raw.get("from", "")))
            target = ensure_node(str(raw.get("to", "")))
            predicate = str(raw.get("type", ""))
            mapping = semantic.relation(predicate)
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
            mapping = semantic.relation("reservation")
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
            mapping = semantic.relation("redress")
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

    def read_observation(self, projection: GraphProjection) -> dict:
        """Read a projected observation back (rule 4: round-trip, field for field).

        Declared nodes, cords, reservations and redress keep the observation's own
        records as attributes; this returns them in projection order. ``redress`` is
        present only when the projection carries any.
        """
        system = projection.nd_systems[0]
        declared = set(system.axes["node_class"].vocabulary or ())
        cord_types = set(system.axes["cord_type"].vocabulary or ())
        observation = {
            "nodes": [dict(n.attributes) for n in projection.nodes if n.node_type in declared],
            "cords": [dict(r.attributes) for r in projection.relations
                      if r.local_predicate in cord_types],
            "reservations": [dict(n.attributes) for n in projection.nodes
                             if n.node_type == "reservation"],
        }
        redress = [dict(n.attributes) for n in projection.nodes if n.node_type == "redress"]
        if redress:
            observation["redress"] = redress
        return observation

    def entry_bindings(self, entry_claims, projection: GraphProjection) -> list[dict]:
        """Claim bindings from versum entries to a projected governance observation.

        ``entry_claims`` are the per-entry plane claims of an index run (rows of
        ``entry_claims.jsonl`` / ``SourceEntries.claims``: ``item_id``, ``plane``,
        ``language_version``, ``claim``). For each governance claim, every form slot
        ``slot -> axis`` binds the entry (``claim_id = item_id``) to the observation
        coordinate with that axis and the claim's value; a claim naming a ``gate``
        binds node coordinates of that gate only. Fails closed: a claim from another
        language version, a named gate the observation does not declare, or a slot with
        no matching coordinate raises ``ValueError``.
        """
        descriptor = self.plane()
        plane_id, version = descriptor["plane"], descriptor["language_version"]
        system = projection.nd_systems[0]
        declared = set(system.axes["node_class"].vocabulary or ())
        node_types = {n.node_id: n.node_type for n in projection.nodes}
        out: list[dict] = []
        seen: set[tuple] = set()
        for row in entry_claims:
            if row.get("plane") != plane_id:
                continue
            item_id, claim = str(row["item_id"]), row["claim"]
            if row.get("language_version") not in (None, version):
                raise ValueError(
                    f"entry {item_id}: claim from governance {row['language_version']!r}, "
                    f"the kit is {version!r} (stale; re-index)")
            gate = claim.get("gate")
            if gate is not None and node_types.get(gate) not in declared:
                raise ValueError(f"entry {item_id}: gate {gate!r} is not declared in the "
                                 f"observation")
            coordinates = claim.get("coordinates") or {}
            for slot, axis in sorted((claim.get("slots") or {}).items()):
                value = coordinates.get(axis)
                matches = [a for a in projection.assignments
                           if a.axis_id == axis and a.value == value
                           and (gate is None or node_types.get(a.subject_id) not in declared
                                or a.subject_id == gate)]
                if not matches:
                    raise ValueError(f"entry {item_id}: slot {slot!r} axis {axis!r} value "
                                     f"{value!r} has no coordinate in the observation")
                for assignment in matches:
                    key = (item_id, assignment.subject_id, axis, slot)
                    if key not in seen:
                        seen.add(key)
                        out.append({"claim_id": item_id, "subject_id": assignment.subject_id,
                                    "axis_id": axis, "form_slot": slot,
                                    "semantic_role": str(claim.get("relation", ""))})
        return out

    def project_entries(self, observation: dict, entry_claims) -> GraphProjection:
        """Project an observation with the entry bindings of an index run, validated."""
        claims = list(entry_claims)
        bindings = self.entry_bindings(claims, self.import_observation(observation))
        return self.import_observation(observation, claim_bindings=bindings)

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
