# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Versum's narrow boundary to the deontic language pack.

Builds the deontic **nD system** (the governance-facet axes deontic content
occupies) from the pack's published vocabulary, so a deontic subgraph can be
stored and queried in Versum's one graph. Consumes the ``deontic`` kit the same
way :mod:`versum.loomground` consumes the governance kit; it reads the pack, adds
no vocabulary of its own.
"""
from __future__ import annotations

import importlib
from typing import Any

from .nd import NDSystem


class DeonticSourceError(RuntimeError):
    """The deontic language pack is absent or incomplete."""


def _kit():
    try:
        kit = importlib.import_module("deontic")
    except ImportError as exc:
        raise DeonticSourceError(
            "the deontic language pack is unavailable; install loomground-deontic"
        ) from exc
    for name in ("VALID_OPERATORS", "INCIDENTS", "language_version"):
        if not hasattr(kit, name):
            raise DeonticSourceError(f"deontic kit is missing {name!r}")
    return kit


def deontic_nd_system() -> NDSystem:
    """The deontic nD system: the operator/incident/party axes a deontic norm
    occupies in Versum's nD (governance) facet, built from the pack's vocabulary."""
    kit = _kit()
    axes: dict[str, Any] = {
        "operator": {"value_type": "controlled_identifier", "vocabulary_mode": "closed",
                     "vocabulary": list(kit.VALID_OPERATORS), "cardinality": "one",
                     "primitives": ["equal"]},
        "incident": {"value_type": "controlled_identifier", "vocabulary_mode": "closed",
                     "vocabulary": list(kit.INCIDENTS), "cardinality": "one",
                     "primitives": ["equal"]},
        "bearer": {"value_type": "entity_reference", "vocabulary_mode": "open",
                   "cardinality": "one", "primitives": ["equal"]},
        "action": {"value_type": "concept_reference", "vocabulary_mode": "open",
                   "cardinality": "one", "primitives": ["equal"]},
        "counterparty": {"value_type": "entity_reference", "vocabulary_mode": "open",
                         "primitives": ["equal"]},
        "condition": {"value_type": "string", "vocabulary_mode": "open",
                      "primitives": ["equal"]},
        "exception": {"value_type": "string", "vocabulary_mode": "open",
                      "primitives": ["equal"]},
        "negated": {"value_type": "boolean", "vocabulary_mode": "open",
                    "cardinality": "one", "primitives": ["equal"]},
    }
    return NDSystem.from_dict({
        "id": "loomground-deontic",
        "namespace": "deontic",
        "version": kit.language_version(),
        "federation_5d_version": "1",
        "axes": axes,
    }).validate()


def register_deontic(registry):
    """Register the deontic nD system in a Versum :class:`~versum.nd.NDRegistry`."""
    return registry.register(deontic_nd_system())
