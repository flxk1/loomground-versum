"""``versum.coordinates`` — entry coordinate queries over an indexed store.

Indexes the committed ``credit_policy_nd`` fixture (the same fixture and exact code
path as ``tests/test_nd_on_index.py``) into ``tmp_path``, then asserts LITERAL results
for :func:`versum.coordinates.entry_coordinates` and :func:`entries_in_cell`, the
fail-closed exceptions on an unknown entry/system/axis, and a CLI round trip through
``versum coords`` / ``versum cell``.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from versum import planes as pl
from versum.coordinates import (
    UnknownAxisError,
    UnknownEntryError,
    UnknownSystemError,
    entries_in_cell,
    entry_coordinates,
)
from versum.store.index import index_folder

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "credit_policy_nd"
POLICY_TEXT = (FIXTURE / "policy.txt").read_text(encoding="utf-8")

DEONTIC_SYSTEM = "loomground-deontic"

# Article -> (operator, bearer, content_text) — mirrors tests/test_nd_on_index.py.
ARTICLES = [
    ("F", "lender", "make a solely automated decision on a credit application"),
    ("P", "lender", "use the score to prepare a decision"),
    ("O", "reviewer", "examine every rejection"),
    ("O", "controller", "inform the applicant of the main factors of the score"),
]


def _rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def indexed(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("coordinates")
    src = root / "src"
    src.mkdir()
    (src / "policy.txt").write_text(POLICY_TEXT, encoding="utf-8")
    out = root / "out"
    manifest = index_folder(src, "law-eu", out, planes=pl.DISCOVER)
    entries = _rows(out / "entries.csv")
    claims = [json.loads(x) for x in
              (out / "entry_claims.jsonl").read_text(encoding="utf-8").splitlines()]
    return {"manifest": manifest, "entries": entries, "claims": claims,
            "out": out, "src": src}


def _norm_entries(indexed: dict) -> list[dict]:
    deontic_ids = {c["item_id"] for c in indexed["claims"] if c["plane"] == "deontic"}
    hits = [e for e in indexed["entries"]
            if e["item_id"] in deontic_ids and e["entry_kind"] == "sentence"]
    return sorted(hits, key=lambda e: int(e["span_start"]))


def _action_type_entry(indexed: dict, norm: dict, content_text: str) -> dict:
    return next(e for e in indexed["entries"]
                if e["parent_id"] == norm["item_id"] and e["text"] == content_text)


# ── entry_coordinates: norm entries ─────────────────────────────────
def test_norm_entry_coordinates_are_literal_per_article(indexed):
    norms = _norm_entries(indexed)
    assert len(norms) == 4
    for idx, (operator, bearer, content_text) in enumerate(ARTICLES):
        norm = norms[idx]
        action = _action_type_entry(indexed, norm, content_text)
        coords = entry_coordinates(indexed["out"], norm["item_id"])
        assert coords["entry_id"] == norm["item_id"]
        assert coords["dimension"] is None, (idx, coords)  # OUGHT: never a 5D dimension
        nd = coords["nd"][DEONTIC_SYSTEM]
        assert nd["operator"] == operator, (idx, nd)
        assert nd["bearer"] == bearer, (idx, nd)
        # the action coordinate is a REFERENCE: the action-type entry's own item_id,
        # never the literal action text a second time
        assert nd["action"] == action["item_id"], (idx, nd)
        assert coords["span"] == (int(norm["span_start"]), int(norm["span_end"]),
                                  norm["text"])
        assert coords["source_urn"] == norm["source_urn"]


def test_action_type_entry_coordinates_carry_the_literal_5d_dimension(indexed):
    norms = _norm_entries(indexed)
    for idx, (_operator, bearer, content_text) in enumerate(ARTICLES):
        norm = norms[idx]
        action = _action_type_entry(indexed, norm, content_text)
        coords = entry_coordinates(indexed["out"], action["item_id"])
        assert coords["dimension"] == "relational", (idx, coords)
        nd = coords["nd"]["loomground-factual"]
        assert nd["subject"] == bearer, (idx, nd)
        assert coords["span"] == (int(action["span_start"]), int(action["span_end"]),
                                  action["text"])
        assert coords["source_urn"] == action["source_urn"]


# ── entries_in_cell ──────────────────────────────────────────────────
def test_entries_in_cell_operator_o_returns_exactly_articles_3_and_4(indexed):
    norms = _norm_entries(indexed)
    expected = [norms[2]["item_id"], norms[3]["item_id"]]
    got = entries_in_cell(indexed["out"], {DEONTIC_SYSTEM: {"operator": "O"}})
    assert got == expected  # deterministic reading order, article 3 before article 4


def test_entries_in_cell_operator_f_returns_exactly_article_1(indexed):
    norms = _norm_entries(indexed)
    got = entries_in_cell(indexed["out"], {DEONTIC_SYSTEM: {"operator": "F"}})
    assert got == [norms[0]["item_id"]]


def test_entries_in_cell_returns_bare_entry_ids_not_dicts(indexed):
    got = entries_in_cell(indexed["out"], {DEONTIC_SYSTEM: {"operator": "P"}})
    assert got and all(isinstance(x, str) for x in got)


# ── fail closed ──────────────────────────────────────────────────────
def test_entry_coordinates_unknown_entry_raises(indexed):
    with pytest.raises(UnknownEntryError):
        entry_coordinates(indexed["out"], "ent-does-not-exist")


def test_entries_in_cell_unknown_system_raises(indexed):
    with pytest.raises(UnknownSystemError):
        entries_in_cell(indexed["out"], {"no-such-system": {"operator": "O"}})


def test_entries_in_cell_unknown_axis_on_known_system_raises(indexed):
    with pytest.raises(UnknownAxisError):
        entries_in_cell(indexed["out"], {DEONTIC_SYSTEM: {"no-such-axis": "x"}})


def test_entries_in_cell_unknown_axis_raises_even_with_no_possible_matches(indexed):
    # fail closed BEFORE scanning rows: an unknown axis must raise even if the
    # otherwise-valid part of the query would match nothing.
    with pytest.raises(UnknownAxisError):
        entries_in_cell(indexed["out"], {DEONTIC_SYSTEM: {"operator": "O",
                                                           "no-such-axis": "x"}})


# ── real coordinates.py behaviour (not simulated) ────────────────────
def test_action_coordinate_is_present_on_every_norm_entry(indexed):
    """A real regression guard for "the norm's own ``action`` coordinate is dropped":
    calls the actual :func:`entry_coordinates` (not a hand-built stand-in dict) and
    asserts the key is present with the expected reference value, for every article."""
    norms = _norm_entries(indexed)
    for idx, (_operator, _bearer, content_text) in enumerate(ARTICLES):
        norm = norms[idx]
        action = _action_type_entry(indexed, norm, content_text)
        coords = entry_coordinates(indexed["out"], norm["item_id"])
        nd = coords["nd"][DEONTIC_SYSTEM]
        assert "action" in nd, (idx, nd)
        assert nd["action"] == action["item_id"], (idx, nd)


def test_entries_in_cell_unknown_axis_raises_before_touching_assignments(indexed, monkeypatch):
    """A real proof that the unknown-axis check happens against the nD registry BEFORE
    any assignment row is read: patch ``load_assignments`` (the only way this function
    reads ``nd/assignments.csv``) to blow up if called, then confirm the unknown-axis
    query still raises ``UnknownAxisError`` — never reaching, let alone silently
    swallowing, that patched call."""
    import versum.coordinates as coordinates_module

    def _boom(path):
        raise AssertionError("entries_in_cell read assignments before validating the axis")

    monkeypatch.setattr(coordinates_module, "load_assignments", _boom)
    with pytest.raises(UnknownAxisError):
        entries_in_cell(indexed["out"], {DEONTIC_SYSTEM: {"no-such-axis": "x"}})


# ── jurisdiction/time sit on source URNs, joined onto entries (item 4) ───
def test_jurisdiction_cell_query_matches_the_sources_entries(tmp_path_factory):
    """Item (4): a ``jurisdiction``/``time`` nD assignment is written once per SOURCE
    URN, never per entry (see ``docs/nd-on-index.md``). This module's chosen resolution
    (documented in ``versum.coordinates``'s module docstring) is an explicit join: both
    ``entry_coordinates`` and ``entries_in_cell`` fold a source's core coordinates onto
    every one of its entries, the same way ``versum.planes.entry_coordinates`` does for
    the plane pipeline itself. Proven here end to end, not simulated."""
    from versum.io.consume import Registry

    root = tmp_path_factory.mktemp("jurisdiction-join")
    src = root / "src"
    src.mkdir()
    (src / "policy.txt").write_text(POLICY_TEXT, encoding="utf-8")
    out = root / "out"
    reg = Registry([{"original_path": "policy.txt", "filename": "policy.txt",
                     "canonical_urn": "urn:dls:test:policy", "jurisdiction": "EU",
                     "detected_year": "2020"}])
    index_folder(src, "law-eu", out, planes=pl.DISCOVER, consume=reg)

    entries = _rows(out / "entries.csv")
    assert entries  # the fixture indexed at least one entry
    got = entries_in_cell(out, {"versum-context": {"jurisdiction": "EU"}})
    assert got, "a real jurisdiction assignment must join onto its source's entries"
    assert set(got) == {e["item_id"] for e in entries}
    for entry_id in got:
        coords = entry_coordinates(out, entry_id)
        assert coords["nd"]["versum-context"]["jurisdiction"] == "EU"


# ── CLI round trip ────────────────────────────────────────────────────
def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "versum", *args],
                          cwd=str(Path(__file__).resolve().parent.parent / "src"),
                          capture_output=True, text=True)


def test_cli_coords_round_trip(indexed):
    norms = _norm_entries(indexed)
    norm = norms[0]
    proc = _run_cli("coords", str(indexed["out"]), norm["item_id"])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    expected = entry_coordinates(indexed["out"], norm["item_id"])
    # ``span`` round-trips through JSON as a list, not a tuple: normalise before the
    # literal equality check so this assertion is real (no always-true escape clause).
    expected = {**expected, "span": list(expected["span"])}
    assert payload == expected
    assert payload["dimension"] is None
    assert payload["nd"][DEONTIC_SYSTEM]["operator"] == "F"


def test_cli_coords_unknown_entry_exits_nonzero(indexed):
    proc = _run_cli("coords", str(indexed["out"]), "ent-does-not-exist")
    assert proc.returncode != 0


def test_cli_cell_round_trip(indexed):
    norms = _norm_entries(indexed)
    proc = _run_cli("cell", str(indexed["out"]),
                    "--where", f"{DEONTIC_SYSTEM}.operator=O")
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    assert got == [norms[2]["item_id"], norms[3]["item_id"]]


def test_cli_cell_unknown_system_exits_nonzero(indexed):
    proc = _run_cli("cell", str(indexed["out"]), "--where", "no-such-system.operator=O")
    assert proc.returncode != 0
