from __future__ import annotations

import pytest

from versum.adapters import (
    AdapterRegistry, SemanticMapping, SystemIdentity, project_structure,
)
from versum.dimensions import Dimension


IDENTITY = SystemIdentity("example", "1", "a" * 64, "example-adapter", "1")


def test_structural_fallback_never_invents_non_structural_semantics():
    projection = project_structure({"actors": [{"id": "a"}], "enabled": True}, IDENTITY)
    assert projection.nodes
    assert projection.relations
    assert {relation.dimension for relation in projection.relations} == {
        Dimension.STRUCTURAL.value}
    assert not projection.assignments
    assert not projection.bindings


def test_semantic_mapping_requires_explicit_federation_dimension():
    mapping = SemanticMapping.from_dict({
        "id": "sample", "version": "1",
        "relations": {"flows": {"dimension": "causal"}},
    })
    assert mapping.relation("flows").dimension == "causal"
    with pytest.raises(ValueError, match="no Federation-5D mapping"):
        mapping.relation("unknown")
    with pytest.raises(ValueError):
        SemanticMapping.from_dict({
            "id": "bad", "version": "1",
            "relations": {"flows": {"dimension": "imaginary"}},
        })


class _Adapter:
    def __init__(self, identity):
        self._identity = identity

    def identity(self):
        return self._identity


def test_adapter_registry_is_collision_safe():
    registry = AdapterRegistry()
    adapter = _Adapter(IDENTITY)
    assert registry.register(adapter) is adapter
    assert registry.for_system("example") is adapter
    assert registry.identities() == (IDENTITY,)
    conflicting = _Adapter(SystemIdentity(
        "example", "2", "b" * 64, "other-adapter", "1"))
    with pytest.raises(ValueError, match="system id"):
        registry.register(conflicting)


def test_adapter_registry_selection_has_no_vendor_name_special_casing():
    """AdapterRegistry.for_system/for_adapter is exact-key lookup, not preference.

    Versum bundles a Loomground adapter (``src/versum/integrations/loomground``),
    but the registry itself must select purely on the identity a caller asks for —
    never by favoring a "loomground"-named system or adapter id over any other
    conforming one. This registers a Loomground-named adapter alongside an
    unrelated one and checks that lookup, collision detection, and ordering all
    treat the two identically: no branch anywhere keys off the string
    "loomground" (or any other vendor name) to prefer one over the other.
    """
    registry = AdapterRegistry()
    loomground_like = _Adapter(SystemIdentity(
        "loomground-governance", "1", "c" * 64, "loomground-federation-5d", "1"))
    other = _Adapter(SystemIdentity(
        "acme-widgets", "1", "d" * 64, "acme-adapter", "1"))

    registry.register(loomground_like)
    registry.register(other)

    # Lookup resolves by the exact id asked for, regardless of registration order
    # or either adapter's name containing "loomground".
    assert registry.for_system("acme-widgets") is other
    assert registry.for_system("loomground-governance") is loomground_like
    assert registry.for_adapter("acme-adapter") is other
    assert registry.for_adapter("loomground-federation-5d") is loomground_like

    # Collision detection applies uniformly: a non-Loomground adapter colliding
    # on id is rejected exactly like a Loomground one would be.
    conflicting = _Adapter(SystemIdentity(
        "acme-widgets", "2", "e" * 64, "other-acme-adapter", "1"))
    with pytest.raises(ValueError, match="system id"):
        registry.register(conflicting)

    # identities() orders by system_id alone (alphabetical), not by vendor
    # identity or registration order — "acme-widgets" sorts before
    # "loomground-governance" on string comparison, with no special-casing either way.
    assert [identity.system_id for identity in registry.identities()] == [
        "acme-widgets", "loomground-governance",
    ]
