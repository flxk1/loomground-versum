"""Turn a missing Loomground adoption kit into a clean skip, not a wall of errors.

Most graph-write tests go through `index()` or `sync_once()`, which stamp the
Loomground grammar fingerprint into every manifest by design (see
docs/decisions/006-shared-source-identity.md). Without the kit installed, each
of those tests would otherwise fail with the same `LoomgroundSourceError`
traceback, obscuring whether a run failed on real breakage or on a missing
dependency. Re-raising as `pytest.skip()` from inside the call itself routes
through pytest's own skip machinery, so reporting behaves exactly like any
other skip in this suite.
"""
from __future__ import annotations

import pytest

from versum.loomground import LoomgroundSourceError


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    try:
        return (yield)
    except LoomgroundSourceError as exc:
        pytest.skip(f"Loomground adoption kit not installed: {exc}")
