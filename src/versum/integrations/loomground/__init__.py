"""Loomground reference implementation of Versum's universal system-adapter protocol."""

from typing import Any

from .adapter import ADAPTER_ID, ADAPTER_VERSION, LoomgroundAdapter, loomground_mapping

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "LOOMGROUND_MAPPING", "LoomgroundAdapter",
           "loomground_mapping"]


def __getattr__(name: str) -> Any:
    # resolved from the kit's governance plane data on access (no copy lives in the versum)
    if name == "LOOMGROUND_MAPPING":
        return loomground_mapping()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
