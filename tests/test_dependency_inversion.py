"""Neutrality guard: no domain leaks into the framework core.

The engine must privilege no domain. This imports only the framework profile machinery
and the generic profile, then reads the core source files and asserts that no
domain-shaped string (a legal marker, a specific domain name, a gold-set term) appears.
Domain vocabulary lives ONLY in profiles; gold sets and corpora are external user data.
"""
from pathlib import Path

from versum.profile import Profile
from versum.profiles.generic import PROFILE as GENERIC

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRAMEWORK = PROJECT_ROOT / "src" / "versum"

# core framework files — must be domain-free
FILES = ["store/graph.py", "io/extract.py", "identity/fingerprint.py", "profile.py", "eval.py",
         "store/index.py", "store/kg.py", "write.py", "identity/urn.py", "identity/core.py",
         "libraries.py", "io/consume.py", "run.py", "materialize.py", "sync.py",
         "concept/canon.py", "concept/morph.py", "store/retrieve.py", "deepen.py"]

# forbidden: legal-marker vocabulary, specific domain names, and gold-set terms.
FORBIDDEN = [
    "celex", "obliged", "principle:high-level-of-protection", "shall",
    "gdpr", "personal-data", "data-protection", "law-eu",
]


def test_generic_profile_is_usable():
    assert isinstance(GENERIC, Profile)
    assert len(GENERIC.predicates) > 0


def test_no_domain_strings_in_core():
    for name in FILES:
        src = (FRAMEWORK / name).read_text(encoding="utf-8").lower()
        for term in FORBIDDEN:
            assert term.lower() not in src, (
                f"{name} contains forbidden domain string {term!r}")


def test_package_has_no_retired_product_dependencies():
    """Distribution metadata must not couple Versum to retired product repositories."""
    metadata = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for retired in ("the-federation", "idea2"):
        assert retired not in metadata
