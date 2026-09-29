"""Single shared helper for the retired-name -> 5D-name deprecation aliases.

Every alias kept for the rename (see the project changelog's "Unreleased" entry)
routes its warning through :func:`warn_renamed` so the wording and stacklevel are
consistent, and so the whole alias surface can be found from one place.
"""
from __future__ import annotations

import warnings


def warn_renamed(old: str, new: str, *, stacklevel: int = 3) -> None:
    """Emit a standard ``DeprecationWarning`` for a retired ``old`` -> ``new`` rename.

    ``stacklevel=3`` is right for the common shape (caller -> alias method/property
    -> this helper); pass a different value when the alias is wrapped in an extra
    frame.
    """
    warnings.warn(
        f"{old!r} is deprecated and will be removed in a future release; use "
        f"{new!r} instead.",
        DeprecationWarning,
        stacklevel=stacklevel,
    )
