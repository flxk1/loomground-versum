"""law-eu German marker: 'unzulässig' is a prohibition.

Much German regulatory law states its core prohibition as '… ist/sind unzulässig' (e.g. UWG §3
'Unlautere geschäftliche Handlungen sind unzulässig'). Without this marker the central
prohibition is missed and the surrounding permissive 'kann'/'darf' clauses dominate, so the
statute reads as mostly permitted. This guards the marker.
"""
from versum.io.extract import candidate_items
from versum.profiles.law_eu import PROFILE as LAW, MARKERS_DE

URN = "urn:dls:sha256:testunzul"


def test_unzulaessig_is_a_registered_prohibition_marker():
    assert ("unzulässig", "prohibits", "prohibited") in MARKERS_DE


def test_unzulaessig_yields_a_prohibition():
    unit = {"text": "Unlautere geschäftliche Handlungen sind unzulässig.", "start": 0,
            "unit_id": "u1", "unit_type": "article"}
    items = candidate_items(unit, URN, LAW)
    prohibitions = [it for it in items if it["modality"] == "prohibited"]
    assert prohibitions, f"'sind unzulässig' should yield a prohibited claim; got {[i['modality'] for i in items]}"
