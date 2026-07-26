"""Versum's narrow boundary to Loomground's neutral language adoption kit."""
from __future__ import annotations

import hashlib
import importlib
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class LoomgroundSourceError(RuntimeError):
    """The declared Loomground adoption kit is absent or incomplete."""


def _kit(source: str | Path | None = None):
    """Import the installed kit, or a local `loomground-governance` checkout for development."""
    try:
        kit = importlib.import_module("loomground_governance")
        if all(hasattr(kit, name) for name in ("grammar", "language_card", "language_version")):
            return kit
    except ImportError:
        pass

    configured = source or os.environ.get("LOOMGROUND_SOURCE")
    if not configured:
        raise LoomgroundSourceError(
            "Loomground adoption kit is unavailable; install loomground-governance "
            "or set LOOMGROUND_SOURCE to a local checkout"
        ) from None
    checkout = Path(configured).expanduser().resolve()
    package_root = checkout / "src"
    if not (package_root / "loomground_governance/__init__.py").is_file():
        raise LoomgroundSourceError(
            f"LOOMGROUND_SOURCE={checkout} does not contain src/loomground_governance"
        )
    sys.modules.pop("loomground_governance", None)
    sys.path.insert(0, str(package_root))
    kit = importlib.import_module("loomground_governance")
    if not all(hasattr(kit, name) for name in ("grammar", "language_card", "language_version")):
        raise LoomgroundSourceError("Loomground adoption kit does not expose the required API")
    return kit


def language_info(source: str | Path | None = None) -> dict[str, Any]:
    """Return identity and a digest of the kit grammar Versum actually consumes."""
    kit = _kit(source)
    card = kit.language_card()
    grammar = kit.grammar()
    return {
        "language": str(card["language"]).lower(),
        "language_version": kit.language_version(),
        "grammar": card["artifacts"]["grammar"],
        "grammar_sha256": hashlib.sha256(grammar.encode("utf-8")).hexdigest(),
        "language_card": card,
    }


def grammar_text(source: str | Path | None = None) -> str:
    """Load the normative EBNF through Loomground's adoption kit."""
    return str(_kit(source).grammar())


def reasoning_request(
    source: str, transport: Mapping[str, Any] | None = None,
    language_source: str | Path | None = None,
) -> dict:
    """Build a neutral request carrying the consumed grammar identity."""
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Loomground source must be a non-empty string")
    info = language_info(language_source)
    return {
        "schema": "reasoning.interop",
        "language": info["language"],
        "language_version": info["language_version"],
        "grammar_sha256": info["grammar_sha256"],
        "source": source,
        "transport": dict(transport or {}),
    }


def canonical_observation(value: Mapping[str, Any]) -> dict:
    """Preserve a runtime observation as interchange data, without interpretation."""
    observation = dict(value)
    for field in ("nodes", "cords", "reservations"):
        if not isinstance(observation.get(field), list):
            raise ValueError(f"canonical observation requires a {field!r} list")
    return observation
