"""Phase 2 — polarity axis in dim5 + nD populated from the registry (loops 3/4).

Proven against the generic profile, a REAL staged 19-column registry sample (set
VERSUM_REGISTRY_CSV to run the registry-backed tests), and .txt fixtures placed at paths
that match registry relpaths (extract works on text via segment_units). Assertions:

  (a) ``polarity`` is a fourth dim5 histogram over the claim's own ``polarity`` value and
      counts a descriptive (``D``) claim;
  (b) indexing a source whose registry row carries jurisdiction='EU' + detected_year='2021'
      yields a fingerprint whose ``nd.jurisdiction`` contains 'EU' and ``nd.time`` '2021',
      while a source with no registry context keeps ``nd`` empty.
"""
import json
import os
from pathlib import Path

import pytest

from versum.io import consume
from versum.io.consume import read_registry
from versum.identity.fingerprint import fingerprint
from versum.store.index import index_folder
from versum.profiles.generic import PROFILE as GENERIC
import versum.profiles  # noqa: F401 — register built-in profiles

URN = "urn:kg:source:demo"


# ── (a) polarity is a fourth dim5 axis and counts a D claim ──────────
def _claims():
    return [
        {"item_id": "i1", "source_urn": URN, "predicate": "defines",
         "modality": "definitional", "quantification": "definite", "polarity": "D"},
        {"item_id": "i2", "source_urn": URN, "predicate": "causes",
         "modality": "asserted", "quantification": "universal", "polarity": "D"},
        {"item_id": "i3", "source_urn": URN, "predicate": "asserts",
         "modality": "asserted", "quantification": "null", "polarity": "N"},
    ]


def test_polarity_is_a_dim5_axis_over_the_claim_value():
    fp = fingerprint(URN, _claims(), GENERIC)
    d = fp["dim5"]
    assert "polarity" in d, "dim5 must carry a polarity histogram"
    # universe is the neutral D/N encoding when the profile exposes no polarities
    assert set(d["polarity"]) == {"D", "N"}
    assert d["polarity"]["D"] == 2   # counts the descriptive claims
    assert d["polarity"]["N"] == 1
    # the other three axes are untouched
    assert d["predicate"]["causes"] == 1
    assert set(d) == {"predicate", "modality", "quantification", "polarity"}


def test_polarity_universe_can_come_from_the_profile():
    class _P:
        id = "p"
        namespace = "kg"
        predicates = frozenset({"defines"})
        modalities = frozenset({"asserted"})
        quantifications = frozenset({"null"})
        polarities = frozenset({"D", "N", "X"})
    fp = fingerprint(URN, _claims(), _P())
    assert set(fp["dim5"]["polarity"]) == {"D", "N", "X"}  # taken from the profile


# ── nd_context populates jurisdiction / time (pure unit) ─────────────
def test_nd_context_populates_jurisdiction_and_time():
    fp = fingerprint(URN, _claims(), GENERIC,
                     nd_context={"jurisdiction": "EU", "time": "2021"})
    assert fp["nd"]["jurisdiction"] == {"EU"}
    assert fp["nd"]["time"] == {"2021"}


def test_no_nd_context_leaves_coordinates_empty():
    fp = fingerprint(URN, _claims(), GENERIC)
    assert fp["nd"]["jurisdiction"] == set()
    assert fp["nd"]["time"] == set()
    # an empty/blank registry value is not invented into a coordinate
    fp2 = fingerprint(URN, _claims(), GENERIC,
                      nd_context={"jurisdiction": "", "time": None})
    assert fp2["nd"]["jurisdiction"] == set() and fp2["nd"]["time"] == set()


# ── (b) index a real-registry-backed source → nd carries EU / 2021 ───
@pytest.fixture(scope="module")
def real_eu_2021_row():
    reg_path = os.environ.get("VERSUM_REGISTRY_CSV")
    if not reg_path or not Path(reg_path).exists():
        pytest.skip("set VERSUM_REGISTRY_CSV to a real staged registry to run this test")
    reg = read_registry(reg_path)
    for r in reg.rows:
        if (r.get("jurisdiction") or "").strip() == "EU" and \
                (r.get("detected_year") or "").strip() == "2021":
            return dict(r)
    pytest.skip("no EU/2021 row in the real registry sample")


def test_indexed_source_fingerprint_nd_from_registry(tmp_path, real_eu_2021_row):
    # a .txt fixture at a relpath the (real-data-derived) registry row points to
    rel = "eu2021/doc.txt"
    f = tmp_path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("The regulation causes an obligation for providers.\n", encoding="utf-8")

    row = dict(real_eu_2021_row)  # real canonical_urn + jurisdiction=EU + detected_year=2021
    row["original_path"] = rel
    row["filename"] = "doc.txt"
    registry = consume.Registry([row])

    manifest = index_folder(tmp_path, profile_id="generic", consume=registry,
                            library="lib", namespace="lib", use_kg_provenance=False)
    fps = json.loads((Path(manifest["out"]) / "fingerprints.json").read_text())

    urn = registry.reuse_urn(relpath=rel)          # reused real canonical_urn
    assert urn and urn in fps
    nd = fps[urn]["nd"]
    assert "EU" in nd["jurisdiction"]              # READ from the registry, not inferred
    assert "2021" in nd["time"]
    # polarity axis survives the index → JSON round-trip
    assert "polarity" in fps[urn]["dim5"]


def test_indexed_source_without_registry_keeps_nd_empty(tmp_path):
    (tmp_path / "plain.txt").write_text(
        "The system causes harm to users.\n", encoding="utf-8")
    manifest = index_folder(tmp_path, profile_id="generic", use_kg_provenance=False)
    fps = json.loads((Path(manifest["out"]) / "fingerprints.json").read_text())
    (nd,) = [v["nd"] for v in fps.values()]
    assert nd["jurisdiction"] == [] and nd["time"] == []  # empty, not invented
