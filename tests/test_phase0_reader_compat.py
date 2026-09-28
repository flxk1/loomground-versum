"""Phase 0 ontology seam, item (3): reader compatibility, the resolve_action_type shim,
and its dated deletion gate.

Mirrors EXACTLY the calls ``ctrl-legal/router/adapters/grounding.py`` makes (read-only;
never edited or imported by this task) in ``read_store()``::

    list(_load_assignments(root / "nd" / "assignments.csv")), \\
        list(_load_claims(root / "claims.csv"))

with ``_load_assignments = versum.nd.load_assignments`` and
``_load_claims = versum.store.graph.load_claims``, same argument shapes (a single
``Path``, positional).
"""
from __future__ import annotations

import csv
import inspect
import shutil
from datetime import date
from pathlib import Path

import pytest

from versum import planes as pl
from versum.nd import ASSIGNMENT_COLUMNS, load_assignments
from versum.store.graph import load_claims
from versum.store.index import index_folder

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "credit_case"
POLICY = FIXTURE / "policy.txt"

# nd/assignments.csv's own column list, frozen independently of versum.nd (Phase 0
# item 3: this must be unchanged by the seam revert).
PRIOR_ASSIGNMENT_COLUMNS = (
    "assignment_id", "subject_id", "system_id", "system_version", "axis_id", "value",
    "source_id", "method", "confidence", "verification")


@pytest.fixture(scope="module")
def store(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("reader_compat")
    src = root / "src"
    src.mkdir()
    shutil.copyfile(POLICY, src / "policy.txt")
    out = root / "out"
    index_folder(src, "law-eu", out, planes=pl.DISCOVER)
    return out


# ── exactly grounding.py's read_store() call shape ──────────────────
def test_read_store_call_shape_exactly_as_grounding_py_makes_it(store):
    root = store
    assignments, claims = (list(load_assignments(root / "nd" / "assignments.csv")),
                           list(load_claims(root / "claims.csv")))
    assert isinstance(assignments, list) and assignments
    assert isinstance(claims, list) and claims


def test_load_assignments_signature_is_a_single_positional_path():
    sig = inspect.signature(load_assignments)
    params = list(sig.parameters.values())
    assert len(params) == 1
    assert params[0].kind in (inspect.Parameter.POSITIONAL_ONLY,
                              inspect.Parameter.POSITIONAL_OR_KEYWORD)
    assert params[0].default is inspect.Parameter.empty


def test_load_claims_signature_is_a_single_positional_path():
    sig = inspect.signature(load_claims)
    params = list(sig.parameters.values())
    assert len(params) == 1
    assert params[0].kind in (inspect.Parameter.POSITIONAL_ONLY,
                              inspect.Parameter.POSITIONAL_OR_KEYWORD)
    assert params[0].default is inspect.Parameter.empty


def test_nd_assignments_csv_column_pin(store):
    assert tuple(ASSIGNMENT_COLUMNS) == PRIOR_ASSIGNMENT_COLUMNS
    with open(store / "nd" / "assignments.csv", newline="", encoding="utf-8") as fh:
        header = tuple(next(csv.reader(fh)))
    assert header == PRIOR_ASSIGNMENT_COLUMNS


def test_grounding_tracked_assignment_columns_present_by_name(store):
    """grounding.py's _build_coordinates reads these columns BY NAME."""
    assignments = list(load_assignments(store / "nd" / "assignments.csv"))
    for row in assignments:
        for col in ("subject_id", "system_id", "axis_id", "value"):
            assert col in row


def test_grounding_tracked_claim_columns_present_by_name(store):
    """grounding.py's _gather_claims reads these columns BY NAME."""
    claims = list(load_claims(store / "claims.csv"))
    for row in claims:
        for col in ("source_urn", "verification", "predicate", "polarity"):
            assert col in row


# ── the resolve_action_type compatibility shim ──────────────────────
def test_shim_resolves_the_action_type_entry_via_embeds(store):
    """A reader still written against the old claims.csv companion-row columns should
    call ``resolve_action_type`` instead of reaching into claims.csv directly; it must
    resolve the SAME action-type entry the structural 'embeds' link points at."""
    entries = {}
    with open(store / "entries.csv", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            entries[row["item_id"]] = row
    links = []
    with open(store / "entry_links.csv", newline="", encoding="utf-8") as fh:
        links = list(csv.DictReader(fh))

    embed_links = [l for l in links if l["relation"] == pl.EMBED_LINK_RELATION
                   and l["dimension"] == pl.EMBED_LINK_DIMENSION]
    # a norm entry (one with an outgoing embeds link whose src is a "sentence" entry
    # that also carries a deontic claim) exists in this fixture -- the acceptance
    # fixture is deontic-rich by construction.
    assert embed_links, "fixture must produce at least one structural embeds link"
    src_id = embed_links[0]["src_id"]
    dst_id = embed_links[0]["dst_id"]

    resolved = pl.resolve_action_type(store, src_id)
    assert resolved is not None
    assert resolved["item_id"] == dst_id == entries[dst_id]["item_id"]


def test_shim_returns_none_for_an_entry_with_no_outgoing_embeds_link(store):
    entries = []
    with open(store / "entries.csv", newline="", encoding="utf-8") as fh:
        entries = list(csv.DictReader(fh))
    links = []
    with open(store / "entry_links.csv", newline="", encoding="utf-8") as fh:
        links = list(csv.DictReader(fh))
    embed_srcs = {l["src_id"] for l in links if l["relation"] == pl.EMBED_LINK_RELATION
                  and l["dimension"] == pl.EMBED_LINK_DIMENSION}
    no_embed = [e for e in entries if e["item_id"] not in embed_srcs]
    assert no_embed, "fixture must produce at least one entry with no outgoing embeds link"
    assert pl.resolve_action_type(store, no_embed[0]["item_id"]) is None


def test_shim_never_fabricates_a_placeholder_for_an_unknown_entry(store):
    assert pl.resolve_action_type(store, "ent-does-not-exist") is None


# ── the shim's dated deletion gate ───────────────────────────────────
def test_shim_deletion_date_constant_is_the_documented_value():
    assert pl.RESOLVE_ACTION_TYPE_DELETION_DATE == "2027-03-31"


def test_shim_must_be_deleted_once_its_own_deletion_date_has_passed():
    """Date-gated: this FAILS the moment today's date exceeds
    ``RESOLVE_ACTION_TYPE_DELETION_DATE`` while ``resolve_action_type`` still exists in
    ``versum.planes`` -- the shim's own docstring commits to deletion by that date, so a
    still-present shim past it is a broken promise, not a passing test."""
    deletion_date = date.fromisoformat(pl.RESOLVE_ACTION_TYPE_DELETION_DATE)
    shim_still_present = hasattr(pl, "resolve_action_type")
    if date.today() > deletion_date:
        assert not shim_still_present, (
            f"resolve_action_type was due for deletion by {deletion_date} "
            f"(see RESOLVE_ACTION_TYPE_DELETION_DATE) and today is {date.today()}, but "
            "the shim is still present in versum.planes")
