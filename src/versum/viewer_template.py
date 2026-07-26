"""Loads the packaged HTML for the self-contained graph viewer.

One file, no network, no dependency: canvas force layout, facet chips built from the
payload's facets (never a hardcoded list), Federation-5D edge colouring, claim polarity
two-tone, search, ego focus on double-click, details panel on click. The markup itself
lives in ``viewer.html``, shipped as package data; ``export.write_html`` substitutes the
``__VERSUM_PAYLOAD__`` token.
"""
from importlib import resources

VIEWER_HTML = resources.files(__package__).joinpath("viewer.html").read_text(encoding="utf-8")
