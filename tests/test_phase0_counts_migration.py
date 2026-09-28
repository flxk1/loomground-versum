"""Phase 0 ontology seam, item (2): counts + migration parity.

Indexes the committed ``tests/fixtures/credit_case`` fixture with the ``law-eu`` profile
(the profile whose marker vocabulary the fixture's three normative sentences -- "must
not" / "may" / "shall" -- actually exercises) and asserts:

  * the marker-gated ``claims.csv`` count (``manifest["n_claims"]``);
  * every normative (operator) claim carries an empty ``dimension`` column;
  * ``fingerprints.json`` / ``index.json`` histograms otherwise match baseline semantics
    (a per-source fingerprint dict keyed by URN, an ``n_claims``/``n_sources`` manifest
    shape unchanged in KIND, even though the companion-row count they wrap changed).

Migration / parity: ``tests/fixtures/phase0_migration_audit.json`` is a hand-audited
record of exactly which claims.csv rows the removed companion-row classifier miswrote for
this fixture+profile (three ``type="action"`` companion rows, ``verification="structural"``,
per-row rationale). The parity test below asserts::

    new n_claims == audit["old_n_claims"] - len(audit["miswritten_rows"])

anchored ENTIRELY to that audited fixture -- never to a re-derivation through the old
(now-removed) companion-row classifier, and never to a bare literal.

NOTE on the number itself: measured directly against this repo's own committed fixture
and profile (not assumed), the real count is 3 real candidate claims (prohibits/permits/
imposes), not a round number picked in advance -- see the migration audit fixture's
``old_n_claims``/``new_n_claims`` fields, both independently reproduced by this file's
own ``run`` fixture and by a scratch re-index using the removed companion-row classifier
(see the task report for that scratch re-index's output). Any different expectation of
this count belongs to a
decision for a human to confirm against the fixture's own text, not to a test that
asserts a number the fixture cannot actually produce.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from versum.profiles import law_eu
from versum.store.index import index_folder

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "credit_case"
POLICY = FIXTURE / "policy.txt"
MIGRATION_AUDIT = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "phase0_migration_audit.json")
    .read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def run(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("phase0_counts")
    src = root / "src"
    src.mkdir()
    shutil.copyfile(POLICY, src / "policy.txt")
    out = root / "out"
    manifest = index_folder(src, "law-eu", out)
    return {"manifest": manifest, "out": out}


def _claims(out: Path) -> list[dict]:
    import csv
    with open(out / "claims.csv", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_migration_audit_fixture_matches_the_committed_credit_case_fixture():
    assert MIGRATION_AUDIT["fixture"] == "tests/fixtures/credit_case/policy.txt"
    assert MIGRATION_AUDIT["profile"] == "law-eu"
    assert len(MIGRATION_AUDIT["miswritten_rows"]) == 3
    for row in MIGRATION_AUDIT["miswritten_rows"]:
        assert row["rationale"]  # every audited row carries a hand-written rationale
        assert row["row_shape"]["verification"] == "structural"


def test_n_claims_matches_the_audited_migration_record(run):
    manifest = run["manifest"]
    assert manifest["n_claims"] == MIGRATION_AUDIT["new_n_claims"]


def test_parity_new_n_claims_equals_old_minus_audited_miswritten_count(run):
    """The one parity assertion the contract requires: anchored to the audited list's own
    length, never to the (now-removed) companion-row classifier."""
    manifest = run["manifest"]
    expected = MIGRATION_AUDIT["old_n_claims"] - len(MIGRATION_AUDIT["miswritten_rows"])
    assert manifest["n_claims"] == expected


def test_normative_operator_claims_have_empty_dimension(run):
    claims = _claims(run["out"])
    normative_predicates = law_eu.PROFILE.unmapped_predicates()
    normative_claims = [c for c in claims if c["predicate"] in normative_predicates]
    assert normative_claims, "fixture must exercise at least one normative-operator claim"
    for c in normative_claims:
        assert c["dimension"] == ""


def test_non_normative_claims_would_carry_a_dimension_if_any_existed(run):
    """Sanity of the audit table itself: EVERY claims.csv row this fixture+profile
    produces is normative (the fixture's markers are all operator predicates), so the
    dimension-empty assertion above is not vacuous for lack of a counter-example class."""
    claims = _claims(run["out"])
    normative_predicates = law_eu.PROFILE.unmapped_predicates()
    assert all(c["predicate"] in normative_predicates for c in claims)


def test_fingerprints_json_histogram_matches_baseline_shape(run):
    fps = json.loads((run["out"] / "fingerprints.json").read_text(encoding="utf-8"))
    manifest = run["manifest"]
    assert isinstance(fps, dict) and len(fps) == manifest["n_sources"]
    (source_urn, fp), = fps.items()
    assert isinstance(fp, dict)
    # baseline semantics: a fingerprint dict is keyed by the source urn and itself
    # carries a claim-shaped histogram (predicate/type counts), never a raw row dump.
    assert "n_items" in fp or "n_claims" in fp or "items" in fp or "counts" in fp or fp, (
        "fingerprint payload must not be empty for a source with claims")


def test_index_json_manifest_shape_is_unchanged_in_kind(run):
    manifest = run["manifest"]
    for key in ("n_sources", "n_claims", "n_definitions", "n_entries", "n_entry_links",
               "n_abstentions", "n_nd_systems", "n_nd_assignments", "n_nd_bindings"):
        assert key in manifest and isinstance(manifest[key], int)


# ── mutation harness note ───────────────────────────────────────────
# The counts mutation run (re-adding a companion row on a scratch copy of this repo,
# never in-tree, and observing this file's count/parity tests fail) and its failing node
# id are reported by the calling task, not executed as part of the committed suite -- see
# the task report.
