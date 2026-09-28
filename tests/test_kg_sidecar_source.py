"""``kg.load_sidecars`` must not drop plane-read source metadata (e.g. topos coordinates)
before it reaches a plane producer's ``context["source"]``.

Regression for the whitelist bug: ``load_sidecars`` used to return only a fixed set of
legacy keys (``canonical_urn``, ``title``, ``pdf_status``, ``verification``,
``authority_tier``, ``topic``, ``subtopic``, ``jurisdiction``, ``year``, ``sidecar``,
``stub``), silently dropping any other sidecar field — including topos axis metadata
(PORT-PLAN.md, "Per-plane mapping", topos row: source metadata -> rank, level, organ).

This file writes its own tmp-dir sidecar inline with literal values (never re-read from
the sidecar/artifact for the assertions) and checks two things:

(i)  ``load_sidecars`` still returns the legacy keys with the same values, unchanged, for
     the existing consumers in ``sync.py`` and ``store/index.py``;
(ii) the complete parsed sidecar — including the topos-shaped fields the legacy whitelist
     does not name — reaches a plane producer as ``context["source"]``, and its values
     appear in the ``versum index`` output (``.versum/nd/assignments.csv``).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from versum.nd import load_assignments
from versum.store import kg
from versum.store.index import index_folder

# A literal sidecar: the legacy fields load_sidecars has always whitelisted, PLUS literal
# topos-shaped fields (rank, level, organ) that the legacy whitelist does not name.
CANONICAL_URN = "urn:dls:celex:32077aa4321"
SIDECAR = {
    "canonical_urn": CANONICAL_URN,
    "title": "Credit Scoring Directive",
    "pdf_status": "available",
    "verification": "verified",
    "authority_tier": "primary",
    "topic": "credit",
    "subtopic": "scoring",
    "jurisdiction": "eu",
    "year": 2024,
    # topos plane metadata — carried by the sidecar but not in the legacy key whitelist
    "rank": "primary-law",
    "level": "supranational",
    "organ": "legislature",
}

# The literal legacy dict load_sidecars has always produced (unchanged by this fix).
EXPECTED_LEGACY = {
    "canonical_urn": CANONICAL_URN,
    "title": "Credit Scoring Directive",
    "pdf_status": "available",
    "verification": "verified",
    "authority_tier": "primary",
    "topic": "credit",
    "subtopic": "scoring",
    "jurisdiction": "eu",
    "year": 2024,
    "sidecar": "policy.txt.metadata.json",
    "stub": "policy.txt",
}

# The literal topos-shaped coordinates a producer should read out of context["source"].
EXPECTED_TOPOS = {"rank": "primary-law", "level": "supranational", "organ": "legislature"}

TOPOS_SYSTEM_ID = "test-topos-shaped-system"
TOPOS_VERSION = "0.0.1-test"


def _topos_shaped_plane() -> dict:
    """A minimal, self-contained plane descriptor (not the real loomground-topos package)
    whose producer reads ``context["source"]["rank"/"level"/"organ"]`` — the same seam the
    real topos plane's ``produce()`` uses (``context.get("source")[axis_name]``) — so this
    test does not depend on any other repo's install state.
    """
    axes = {
        name: {"value_type": "string", "vocabulary_mode": "open", "cardinality": "one"}
        for name in ("rank", "level", "organ")
    }
    nd_system = {
        "id": TOPOS_SYSTEM_ID, "namespace": "test.topos-shaped", "version": TOPOS_VERSION,
        "axes": axes, "bindings": [], "validation": {"unknown_values": "reject"},
    }

    def produce(sentence: str, context: dict | None = None) -> list[dict]:
        source = (context or {}).get("source") or {}
        coords = {k: source[k] for k in ("rank", "level", "organ") if k in source}
        if not coords:
            return []
        return [{"relation": "topos.position", "span": [0, len(sentence)],
                 "coordinates": coords, "slots": {}, "method": "test-rule"}]

    return {
        "plane": "topos-shaped-test", "language_version": TOPOS_VERSION,
        "nd_system": nd_system, "binding": {"topos.position": "structural"},
        "produce": produce, "examples": [],
    }


def _stage(root: Path) -> None:
    # filename shares the sidecar's structured id token with the canonical_urn, so
    # kg.provenance_urn_for matches this file to the sidecar deterministically (the
    # same match kind used across the folder-wide KG-provenance join).
    (root / "CELEX_32077AA4321.txt").write_text(
        "The bank is a controller. The scoring model is part of the credit system.\n",
        encoding="utf-8")
    (root / "CELEX_32077AA4321.txt.metadata.json").write_text(
        json.dumps(SIDECAR, ensure_ascii=False), encoding="utf-8")


# ── (i) legacy keys/values unchanged ───────────────────────────────
def test_load_sidecars_keeps_legacy_keys_and_values_unchanged(tmp_path):
    (tmp_path / "policy.txt").write_text("irrelevant\n", encoding="utf-8")
    (tmp_path / "policy.txt.metadata.json").write_text(
        json.dumps(SIDECAR, ensure_ascii=False), encoding="utf-8")

    sidecars = kg.load_sidecars(tmp_path)

    assert len(sidecars) == 1
    got = sidecars[0]
    legacy = {k: got[k] for k in EXPECTED_LEGACY}
    assert legacy == EXPECTED_LEGACY


def test_load_sidecars_carries_the_complete_parsed_sidecar(tmp_path):
    (tmp_path / "policy.txt").write_text("irrelevant\n", encoding="utf-8")
    (tmp_path / "policy.txt.metadata.json").write_text(
        json.dumps(SIDECAR, ensure_ascii=False), encoding="utf-8")

    sidecars = kg.load_sidecars(tmp_path)

    assert len(sidecars) == 1
    assert sidecars[0]["raw"] == SIDECAR
    # literal check the legacy whitelist alone would have dropped
    assert sidecars[0]["raw"]["rank"] == "primary-law"
    assert sidecars[0]["raw"]["level"] == "supranational"
    assert sidecars[0]["raw"]["organ"] == "legislature"


# ── (ii) topos-shaped metadata reaches context["source"] / the index output ─
def test_sidecar_topos_metadata_reaches_producer_context_and_index_output(tmp_path):
    _stage(tmp_path)

    manifest = index_folder(tmp_path, "generic", planes=[_topos_shaped_plane])

    assert manifest["n_kg_reused"] == 1  # the one source file, keyed on the sidecar's urn
    assignments = load_assignments(tmp_path / ".versum" / "nd" / "assignments.csv")
    topos_rows = [a for a in assignments if a["system_id"] == TOPOS_SYSTEM_ID]
    assert topos_rows, "topos-shaped coordinates never reached the index output"
    got = {a["axis_id"]: a["value"] for a in topos_rows}
    assert got == EXPECTED_TOPOS

    # also visible directly on entries.csv / entry_claims.jsonl (index output)
    claims_path = tmp_path / ".versum" / "entry_claims.jsonl"
    claim_lines = [json.loads(line) for line in
                   claims_path.read_text(encoding="utf-8").splitlines() if line]
    topos_claims = [c for c in claim_lines if c.get("claim", {}).get("relation")
                    == "topos.position"]
    assert topos_claims
    assert topos_claims[0]["claim"]["coordinates"] == EXPECTED_TOPOS

    with open(tmp_path / ".versum" / "sources.csv", newline="", encoding="utf-8") as fh:
        sources = list(csv.DictReader(fh))
    assert sources[0]["canonical_urn"] == CANONICAL_URN
    assert sources[0]["provenance"] == "kg-canonical"
