"""Differential conformance against the claim-axes companion vectors (P4).

The canonical vectors live in the language repo
(``standard/companions/claim-axes/vectors``); ``tests/fixtures/claim_axes_vectors``
is this repo's vendored copy. Versum is the companion's *producer*
implementation: ``conforms`` below restates the companion's bounds
independently of the Solver decoder, must reproduce every vector's flag, and
every record ``candidate_from_claim`` emits must pass it.
"""
import json
from pathlib import Path

import pytest

from versum.reasoning import candidate_from_claim

VECTORS = Path(__file__).resolve().parent / "fixtures" / "claim_axes_vectors"
SCHEMA = "loomground.versum.claim-axes/v1"
AXES = ("predicate", "modality", "polarity", "quantification", "domain")
MAX_VALUE = 256


def conforms(record) -> bool:
    """Versum's statement of the companion bounds (COMPANION.md §2)."""
    if not isinstance(record, dict) or set(record) != {"schema", "axes"}:
        return False
    if record["schema"] != SCHEMA or not isinstance(record["axes"], dict):
        return False
    for axis, value in record["axes"].items():
        if axis not in AXES:
            return False
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_VALUE:
            return False
    return True


def _vectors():
    manifest = json.loads((VECTORS / "manifest.json").read_text())
    return [json.loads((VECTORS / name).read_text()) for name in manifest["vectors"]]


@pytest.mark.parametrize("vector", _vectors(), ids=lambda v: v["name"])
def test_producer_rules_reproduce_every_companion_vector(vector):
    assert conforms(vector["record"]) == vector["valid"], vector["description"]


@pytest.mark.parametrize("extra", [
    {},
    {"predicate": "causes", "modality": "asserted", "polarity": "D",
     "quantification": "universal", "domain": "law"},
    {"predicate": "defines"},
])
def test_emitted_records_conform(extra):
    row = {"canonical_urn": "urn:test:doc", "item_id": "claim-1",
           "text": "Negligence causes breaches.", "span_start": "0",
           "span_end": "27", "content_digest": "sha256:" + "a" * 64, **extra}
    candidate = candidate_from_claim(row, graph_version="sha256:" + "1" * 64)
    assert conforms(candidate.structural_evidence)


def test_vendored_copy_matches_the_canonical_vectors_when_present():
    canonical = (Path(__file__).resolve().parents[2] / "loomground-governance"
                 / "standard" / "companions" / "claim-axes" / "vectors")
    if not canonical.is_dir():
        pytest.skip("language repo not available")
    for path in sorted(VECTORS.glob("*.json")):
        assert (canonical / path.name).read_text() == path.read_text(), (
            f"{path.name} drifted from the canonical companion copy")
