# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 flxk1
"""Versum's narrow boundary to the deontic language pack.

The deontic **nD system** (the axes deontic content occupies) and the deontic
relation → 5D **binding** are the plane's own published documents: the versum
reads them from the plane descriptor the pack registers under the
``loomground.planes`` entry point (``deontic``), validated by
:class:`versum.planes.DescriptorPlane`. Consumes the ``deontic`` kit the same way
:mod:`versum.loomground` consumes the governance kit; it adds no vocabulary, no
axis and no dimension of its own.
"""
from __future__ import annotations

import importlib
import importlib.metadata

from .nd import NDSystem
from .planes import ENTRY_POINT_GROUP, DescriptorPlane, PlaneDescriptorError

DEONTIC_PLANE_ID = "deontic"


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


def deontic_plane() -> DescriptorPlane:
    """The deontic plane, loaded from its ``loomground.planes`` entry point and
    validated against the plane descriptor contract (fail closed)."""
    _kit()
    eps = [ep for ep in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
           if ep.name == DEONTIC_PLANE_ID]
    if len(eps) != 1:
        raise DeonticSourceError(
            f"the deontic pack publishes {len(eps)} {ENTRY_POINT_GROUP!r} entry points "
            f"named {DEONTIC_PLANE_ID!r}; install a loomground-deontic that publishes "
            "its plane descriptor")
    try:
        factory = eps[0].load()
        return DescriptorPlane.from_descriptor(factory(), entry_name=DEONTIC_PLANE_ID)
    except PlaneDescriptorError as exc:
        raise DeonticSourceError(f"the deontic plane descriptor is invalid: {exc}") from exc
    except Exception as exc:
        raise DeonticSourceError(
            f"the deontic plane failed to load: {type(exc).__name__}: {exc}") from exc


def deontic_binding() -> dict[str, str]:
    """The deontic relation → 5D binding, as the plane publishes it
    (operator → dimension; one of the five dimensions only)."""
    return dict(deontic_plane().binding())


def deontic_nd_system() -> NDSystem:
    """The deontic nD system: the operator/incident/party axes a deontic norm
    occupies, exactly as the plane publishes it (``nd-system.json``)."""
    return deontic_plane().nd_system()


def register_deontic(registry):
    """Register the deontic nD system in a Versum :class:`~versum.nd.NDRegistry`."""
    return registry.register(deontic_nd_system())
