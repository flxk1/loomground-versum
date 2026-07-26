"""Collision-safe adapter discovery by system id and adapter id."""
from __future__ import annotations

from .intermediate import SystemIdentity
from .protocol import SystemAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._by_system: dict[str, SystemAdapter] = {}
        self._by_adapter: dict[str, SystemAdapter] = {}

    def register(self, adapter: SystemAdapter) -> SystemAdapter:
        identity = adapter.identity()
        for index, key, label in (
            (self._by_system, identity.system_id, "system"),
            (self._by_adapter, identity.adapter_id, "adapter"),
        ):
            existing = index.get(key)
            if existing is not None and existing.identity() != identity:
                raise ValueError(f"different adapters claim {label} id {key!r}")
            index[key] = adapter
        return adapter

    def for_system(self, system_id: str) -> SystemAdapter:
        return self._by_system[system_id]

    def for_adapter(self, adapter_id: str) -> SystemAdapter:
        return self._by_adapter[adapter_id]

    def identities(self) -> tuple[SystemIdentity, ...]:
        return tuple(sorted((adapter.identity() for adapter in self._by_system.values()),
                            key=lambda identity: identity.system_id))
