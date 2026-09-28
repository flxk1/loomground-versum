"""Phase 0 versum smoke test: the committed ``credit_case`` fixture indexes end to end
through the real, installed deontic language pack -- the '## versum' blocker recorded in
phase1-findings.md (``PlaneIndexError`` on ``exception_status``, an nD axis
``deontic.plane.plane()`` emitted but never declared) is resolved.

Asserts, on the norm "The controller must not make a solely automated decision on a
credit application.":
  * ``versum.store.index.index_folder`` raises no ``PlaneIndexError`` indexing
    ``tests/fixtures/credit_case/policy.txt`` with the real ``deontic`` + ``factual``
    planes installed (``deontic.produce()`` publishes ``exception_status``; the deontic
    nD system declares it -- see ``deontic/artifacts/nd-system.json``);
  * the norm's content ("make a solely automated decision on a credit application")
    lands as its own, separate entry -- NOT ASSERTED (never a row in ``claims.csv``,
    the store's asserted-claim write surface; see docs/architecture/planes.md, "Round 7")
    -- linked from the norm's own entry by the structural ``embeds`` relation;
  * the deontic plane's own ``action`` coordinate is repointed from literal text to a
    concept reference (the content entry's ``item_id``) -- never asserting the action
    into the norm's own coordinates a second time;
  * the deontic plane's 5D binding is empty (``{}``): O/P/F is an ought, never a fact on
    the 5D manifold -- no operator value is ever carried on a 5D dimension.

This test is written to FAIL if ``exception_status`` is ever removed from the deontic
plane's declared nD axes (or from what ``produce()`` emits): both are asserted directly
below, and ``index_folder`` itself would raise ``PlaneIndexError`` again exactly as
before this axis was declared (the original blocker).
"""
from __future__ import annotations

import csv
import importlib.metadata
import json
import shutil
from pathlib import Path

import pytest

from versum import planes as pl
from versum.deontic import deontic_plane
from versum.store.index import index_folder

import deontic  # noqa: E402 -- a hard dependency; never skipped

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "credit_case"
POLICY = FIXTURE / "policy.txt"
NORM_TEXT = ("The controller must not make a solely automated decision on a credit "
             "application.")
CONTENT_TEXT = "make a solely automated decision on a credit application"


def _rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _factual_plane() -> pl.DescriptorPlane:
    """The real, installed ``factual`` plane -- loaded the same way
    :func:`versum.deontic.deontic_plane` loads deontic, so a norm's content can be
    lowered and linked by ``embeds`` (see ``versum.planes.build_source_entries``,
    "A norm's content" comment)."""
    eps = [ep for ep in importlib.metadata.entry_points(group=pl.ENTRY_POINT_GROUP)
           if ep.name == "factual"]
    assert len(eps) == 1, "expected exactly one installed 'factual' loomground.planes entry point"
    factory = eps[0].load()
    return pl.DescriptorPlane.from_descriptor(factory(), entry_name="factual")


@pytest.fixture(scope="module")
def indexed_credit_case(tmp_path_factory) -> dict:
    """Index the committed ``credit_case`` fixture through the real deontic + factual
    planes -- the exact precondition the '## versum' blocker names."""
    root = tmp_path_factory.mktemp("credit_fixture_smoke")
    src = root / "src"
    src.mkdir()
    shutil.copyfile(POLICY, src / "policy.txt")
    out = root / "out"
    manifest = index_folder(src, "generic", out, planes=[deontic_plane(), _factual_plane()])
    entries = _rows(out / "entries.csv")
    links = _rows(out / "entry_links.csv")
    claims_csv = _rows(out / "claims.csv") if (out / "claims.csv").exists() else []
    entry_claims = [json.loads(x) for x in
                    (out / "entry_claims.jsonl").read_text(encoding="utf-8").splitlines()]
    return {"manifest": manifest, "entries": entries, "links": links,
            "claims_csv": claims_csv, "entry_claims": entry_claims, "out": out}


# ── the blocker itself: no PlaneIndexError, ever ────────────────────────
def test_index_folder_does_not_raise_planeindexerror_on_the_credit_fixture():
    """The precondition ``index_folder`` blocked on before this axis was declared."""
    root = Path("/tmp")  # unused; index_folder never opens this path
    del root
    # a bare re-run, isolated from the module fixture, so a regression here is loud and
    # local rather than hidden behind the fixture's caching.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "src"
        src.mkdir()
        shutil.copyfile(POLICY, src / "policy.txt")
        try:
            index_folder(src, "generic", Path(td) / "out",
                        planes=[deontic_plane(), _factual_plane()])
        except pl.PlaneIndexError as exc:  # pragma: no cover - only on regression
            pytest.fail(f"index_folder raised PlaneIndexError: {exc}")


# ── declared axis: the test fails if exception_status regresses ────────
def test_exception_status_is_a_declared_deontic_axis_and_is_emitted():
    plane = deontic_plane()
    assert "exception_status" in plane.nd_system().axes, (
        "exception_status must stay a declared deontic nD axis -- its absence is exactly "
        "the '## versum' blocker (PlaneIndexError: unknown nD axis 'exception_status')")
    claims = plane.produce(NORM_TEXT)
    assert claims and "exception_status" in claims[0]["coordinates"]


# ── the norm's content: a not-asserted entry, linked by 'embeds' ───────
def test_norm_content_lands_as_a_not_asserted_entry_linked_by_embeds(indexed_credit_case):
    entries = indexed_credit_case["entries"]
    entry_claims = indexed_credit_case["entry_claims"]
    links = indexed_credit_case["links"]
    claims_csv = indexed_credit_case["claims_csv"]

    (norm_entry,) = [e for e in entries if e["text"] == NORM_TEXT]
    (content_entry,) = [e for e in entries if e["text"] == CONTENT_TEXT]
    assert content_entry["entry_kind"] == "embedded"
    assert content_entry["parent_id"] == norm_entry["item_id"]

    embeds = [l for l in links if l["src_id"] == norm_entry["item_id"]
              and l["dst_id"] == content_entry["item_id"]]
    assert len(embeds) == 1 and embeds[0]["relation"] == pl.EMBED_LINK_RELATION

    # NOT ASSERTED: the content entry never reaches claims.csv (the store's asserted-claim
    # write surface -- docs/architecture/planes.md, "Round 7"). It is readable only
    # through the entry model / resolve_action_type, never as a candidate/confirmed/
    # attested claim row.
    asserted_ids = {row.get("item_id") for row in claims_csv}
    assert content_entry["item_id"] not in asserted_ids

    # It also carries no deontic (or any) claim of its own in entry_claims.jsonl keyed to
    # the deontic plane -- the norm's own deontic claim is the only deontic assertion.
    deontic_claim_ids = {c["item_id"] for c in entry_claims if c["plane"] == "deontic"}
    assert content_entry["item_id"] not in deontic_claim_ids
    assert norm_entry["item_id"] in deontic_claim_ids


# ── the deontic `action` coordinate references the content entry ──────
def test_deontic_action_coordinate_references_the_content_entry(indexed_credit_case):
    out = indexed_credit_case["out"]
    from versum.nd import load_assignments
    entries = indexed_credit_case["entries"]
    (norm_entry,) = [e for e in entries if e["text"] == NORM_TEXT]
    (content_entry,) = [e for e in entries if e["text"] == CONTENT_TEXT]

    rows = load_assignments(out / "nd" / "assignments.csv")
    coords = {r["axis_id"]: r["value"] for r in rows
              if r["subject_id"] == norm_entry["item_id"] and r["system_id"] == "loomground-deontic"}
    assert coords["operator"] == "F"
    assert coords["exception_status"] == "none_detected"
    # the action coordinate is a reference to the content entry's item_id -- never the
    # literal action text a second time.
    assert coords["action"] == content_entry["item_id"]
    assert coords["action"] != CONTENT_TEXT


# ── O/P/F carries no 5D dimension ───────────────────────────────────────
def test_deontic_operator_carries_no_5d_dimension():
    """Round 4: an operator (O/P/F) is an ought, not a fact on the 5D manifold -- the
    deontic plane's binding is always empty, so no axis (least of all `operator`) is ever
    mapped onto a 5D dimension."""
    plane = deontic_plane()
    assert plane.binding() == {}


def test_no_5d_dimension_value_on_any_entry_is_an_operator_letter(indexed_credit_case):
    """Literal per-row check: entries.csv's five dimension columns are floats; none of
    them is ever the string 'O', 'P' or 'F' -- an operator value never appears on a 5D
    dimension under any name."""
    from versum import position5d as p5
    for e in indexed_credit_case["entries"]:
        for dim in p5.DIMENSIONS:
            assert e[dim] not in ("O", "P", "F")
