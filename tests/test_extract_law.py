"""Extract a real CELEX PDF with the law-eu profile and check the candidate claims.

Set VERSUM_CELEX_PDF to a local CELEX 52012PC0011 PDF to run this test; it is the user's
own staged data, not something the engine ships.
"""
import os
from pathlib import Path

import pytest

from versum.io.extract import extract
from versum.profiles.law_eu import PROFILE as LAW

_CELEX_PDF = os.environ.get("VERSUM_CELEX_PDF")
CELEX_PDF = Path(_CELEX_PDF) if _CELEX_PDF else None
URN_A = "urn:dls:celex:52012pc0011"

pytestmark = pytest.mark.skipif(
    not (CELEX_PDF and CELEX_PDF.exists()),
    reason="set VERSUM_CELEX_PDF to a local CELEX PDF to run this test")


def test_extract_law_celex():
    result = extract(str(CELEX_PDF), URN_A, LAW)
    items = result["items"]

    assert len(items) > 100, f"expected >100 candidate claims, got {len(items)}"

    for it in items:
        # every closed axis value is valid under the active profile
        assert LAW.is_valid("predicate", it["predicate"]), it["predicate"]
        assert LAW.is_valid("modality", it["modality"]), it["modality"]
        assert LAW.is_valid("quantification", it["quantification"]), it["quantification"]
        # every claim traces to the source urn + a char span
        assert it["source_urn"] == URN_A
        assert isinstance(it["span"], list) and len(it["span"]) == 2
        assert it["span"][0] <= it["span"][1]
        # candidate substrate; curation-only axes untouched
        assert it["verification"] == "candidate"
        assert it["principle"] is None
        assert it["inference_rule"] == "unspecified"
