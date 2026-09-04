"""law-eu CELEX identity keeps the consolidation-date suffix.

A consolidated EUR-Lex text (sector ``0``) is a distinct document per in-force date. Before
the fix the profile's CELEX resolver stopped after the optional ``_sum``/``_inf`` qualifier,
so ``02024R1689-20260727`` and ``02024R1689-20240801`` both minted ``urn:dls:celex:02024r1689``
— two point-in-time versions collapsed to one identity, defeating any as-of-date question.
The resolver now carries an optional trailing ``-YYYYMMDD`` inside the single captured id.
"""
from pathlib import Path

from versum.identity.core import deterministic_identity
from versum.profile import get_profile
import versum.profiles  # noqa: F401 — register built-ins

LAW_EU = get_profile("law-eu")


def _urn(tmp_path: Path, name: str) -> str:
    f = tmp_path / name
    f.write_text("Article 1\nThe provider shall ensure compliance.\n", encoding="utf-8")
    return deterministic_identity(str(f), LAW_EU)[0]


def test_two_consolidation_dates_mint_distinct_urns(tmp_path):
    a = _urn(tmp_path, "CELEX_02024R1689-20260727.txt")
    b = _urn(tmp_path, "CELEX_02024R1689-20240801.txt")
    assert a == "urn:dls:celex:02024r1689-20260727"
    assert b == "urn:dls:celex:02024r1689-20240801"
    assert a != b  # the collision the fix closes


def test_bare_celex_is_unchanged(tmp_path):
    # backward-compat: a suffix-less CELEX mints exactly what it always did (zero migration).
    assert _urn(tmp_path, "CELEX_32024R1689.txt") == "urn:dls:celex:32024r1689"


def test_sum_qualifier_still_captured_alongside_date(tmp_path):
    # the pre-existing _sum/_inf capture is preserved; date is additive, not a replacement.
    assert _urn(tmp_path, "CELEX_62018CJ0018_SUM.txt") == "urn:dls:celex:62018cj0018_sum"
