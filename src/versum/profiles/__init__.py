"""Built-in profiles. Importing this package registers them in the PROFILES registry.

New domains add a module here that builds a ``Profile`` and calls ``register(...)``,
then import it below. The framework never imports a profile by name — it resolves via
``get_profile(id)`` at call time.
"""
from . import generic    # noqa: F401 — self-registers "generic"
from . import law_eu     # noqa: F401 — self-registers "law-eu"
from . import news       # noqa: F401 — self-registers "news"
from . import scholarly  # noqa: F401 — self-registers "scholarly"

__all__ = ["generic", "law_eu", "news", "scholarly"]
