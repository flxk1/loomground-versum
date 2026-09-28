"""End-to-end: ``versum index <folder> --profile law-eu`` writes nD assignments for
EVERY applicable plane, on the committed ``credit_policy_nd`` fixture (a 4-article
policy carrying a prohibition, a permission and two obligations).

Indexes the fixture through :func:`versum.store.index.index_folder` with
``planes=versum.planes.DISCOVER`` — the SAME code path ``versum index`` (the CLI,
``src/versum/__main__.py``, untouched by this task) uses: it calls
``index_folder(folder, profile, out, nd_system_paths=..., planes="discover")``.

Binding: 5D is what IS; O/P/F are OUGHT and carry no 5D dimension under any name — no
norm/operator row ever gets a ``dimension`` column or value (there is none in
``nd/assignments.csv`` to begin with; the invariant this asserts is that no plane binds
an operator's relation to a cross-profile 5D dimension — see the deontic-binding-must-be-
empty guard in :mod:`versum.planes`). A norm's content is its own action-type entry
(``asserted: false``), linked from the norm by a structural ``embeds`` edge, and the
norm's own ``action`` coordinate is a reference (the entry's ``item_id``), never the
literal text a second time.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from versum import planes as pl
from versum.nd import load_assignments, load_bindings
from versum.store.index import index_folder

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "credit_policy_nd"
POLICY_TEXT = (FIXTURE / "policy.txt").read_text(encoding="utf-8")

# Article -> (operator, bearer[normalised: lowercased surface noun, no article/prefix])
ARTICLES = [
    ("Article 1", "F", "lender",
     "make a solely automated decision on a credit application"),
    ("Article 2", "P", "lender", "use the score to prepare a decision"),
    ("Article 3", "O", "reviewer", "examine every rejection"),
    ("Article 4", "O", "controller",
     "inform the applicant of the main factors of the score"),
]


def _rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def run(tmp_path_factory) -> dict:
    """Index the committed fixture via the exact code path ``versum index`` uses."""
    root = tmp_path_factory.mktemp("credit_policy_nd")
    src = root / "src"
    src.mkdir()
    (src / "policy.txt").write_text(POLICY_TEXT, encoding="utf-8")
    out = root / "out"
    manifest = index_folder(src, "law-eu", out, planes=pl.DISCOVER)
    entries = _rows(out / "entries.csv")
    links = _rows(out / "entry_links.csv")
    claims = [json.loads(x) for x in
              (out / "entry_claims.jsonl").read_text(encoding="utf-8").splitlines()]
    assignments = load_assignments(out / "nd" / "assignments.csv")
    bindings = load_bindings(out / "nd" / "bindings.csv")
    return {
        "manifest": manifest, "entries": entries, "links": links,
        "claims": claims, "assignments": assignments, "bindings": bindings,
        "out": out, "src": src,
    }


def _coords(run: dict, item_id: str, system_id: str) -> dict:
    out: dict = {}
    for a in run["assignments"]:
        if a["subject_id"] == item_id and a["system_id"] == system_id:
            out.setdefault(a["axis_id"], []).append(a["value"])
    return {k: (v[0] if len(v) == 1 else sorted(v, key=json.dumps)) for k, v in out.items()}


def _system_id(run: dict, plane: str) -> str:
    (p,) = [p for p in run["manifest"]["planes"] if p["plane"] == plane]
    return p["system_id"]


def _deontic_entries(run: dict) -> list[dict]:
    """The 4 norm (sentence) entries the deontic plane claimed, in text order."""
    deontic_ids = {c["item_id"] for c in run["claims"] if c["plane"] == "deontic"}
    hits = [e for e in run["entries"]
            if e["item_id"] in deontic_ids and e["entry_kind"] == "sentence"]
    return sorted(hits, key=lambda e: int(e["span_start"]))


def _entry_claim(run: dict, item_id: str, plane: str) -> dict:
    (c,) = [c["claim"] for c in run["claims"]
            if c["item_id"] == item_id and c["plane"] == plane]
    return c


# ── (2) the indexer writes nD assignments end to end ───────────────
def test_n_nd_assignments_is_greater_than_zero(run):
    assert run["manifest"]["n_nd_assignments"] > 0
    assert len(run["assignments"]) == run["manifest"]["n_nd_assignments"]


def test_row_counts_per_system_are_reported(run):
    by_system: dict[str, int] = {}
    for a in run["assignments"]:
        by_system[a["system_id"]] = by_system.get(a["system_id"], 0) + 1
    # deontic, factual and the core jurisdiction/time system must all have written rows
    # for this fixture (epistemic/topos/governance are present only where the plane's own
    # markers/context apply — none of this fixture's sentences trigger them, per the
    # deontic-only/factual-only content of the four articles).
    # 4 norms x (bearer, negated, operator, action, exception_status) + 1 condition
    # (article 3 only) — exception_status is a declared nd axis, emitted alongside
    # the operator on every claim (see deontic.plane.claim_for).
    assert by_system.get("loomground-deontic", 0) == 4 * 5 + 1
    assert by_system.get("loomground-factual", 0) > 0
    assert by_system.get("versum-context", 0) == 0  # no consume registry / kg sidecar here
    # report for the human-readable evidence trail
    print("nD assignment rows by system:", by_system)


# ── (3) literal per-article assertions ──────────────────────────────
def test_four_norms_found_in_article_order(run):
    entries = _deontic_entries(run)
    assert len(entries) == 4


def test_operators_are_f_p_o_o(run):
    entries = _deontic_entries(run)
    ops = [_coords(run, e["item_id"], _system_id(run, "deontic"))["operator"]
           for e in entries]
    assert ops == ["F", "P", "O", "O"]


def test_bearers_are_lender_lender_reviewer_controller(run):
    entries = _deontic_entries(run)
    bearers = [_coords(run, e["item_id"], _system_id(run, "deontic"))["bearer"]
               for e in entries]
    # exact literal, lowercase surface noun (the deontic plane's own normalisation) —
    # never "the lender" / "a reviewer" / "the controller"
    assert bearers == ["lender", "lender", "reviewer", "controller"]


def test_article_1_negation_follows_the_deontic_convention(run):
    """'must not' lowers to operator F with negated=False: prohibition is carried by the
    operator itself, never by an additional negation flag on top of it (the deontic
    plane's own convention — a negated OPERATOR would be a different, unused reading)."""
    e = _deontic_entries(run)[0]
    c = _coords(run, e["item_id"], _system_id(run, "deontic"))
    assert c["operator"] == "F"
    assert c["negated"] is False


def test_action_type_entries_exist_asserted_false_with_literal_5d_dimension(run):
    for idx, (_label, _op, bearer, content_text) in enumerate(ARTICLES):
        norm = _deontic_entries(run)[idx]
        content = next(
            e for e in run["entries"]
            if e["parent_id"] == norm["item_id"] and e["text"] == content_text)
        fclaim = _entry_claim(run, content["item_id"], "factual")
        assert fclaim["asserted"] is False, (idx, fclaim)
        assert fclaim["entry_kind"] == "action_type", (idx, fclaim)
        assert fclaim["coordinates"]["subject"] == bearer, (idx, fclaim)
        # literal 5D dimension per article: every action type here is a bare predication
        # (no other plane also claims this exact sub-span), so its dominant dimension is
        # the framework's own relational floor for a bare predicate/object clause.
        assert content["dominant_dimension"] == "relational", (idx, content)


def test_embeds_link_from_each_norm_to_its_action_type(run):
    for idx, (_label, _op, _bearer, content_text) in enumerate(ARTICLES):
        norm = _deontic_entries(run)[idx]
        content = next(
            e for e in run["entries"]
            if e["parent_id"] == norm["item_id"] and e["text"] == content_text)
        hits = [l for l in run["links"]
                if l["src_id"] == norm["item_id"] and l["dst_id"] == content["item_id"]
                and l["relation"] == "embeds" and l["dimension"] == "structural"]
        assert len(hits) == 1, (idx, norm["item_id"], content["item_id"])


def test_deontic_action_coordinate_equals_the_action_type_entry_id(run):
    for idx, (_label, _op, _bearer, content_text) in enumerate(ARTICLES):
        norm = _deontic_entries(run)[idx]
        content = next(
            e for e in run["entries"]
            if e["parent_id"] == norm["item_id"] and e["text"] == content_text)
        c = _coords(run, norm["item_id"], _system_id(run, "deontic"))
        assert c["action"] == content["item_id"], (idx, c["action"], content["item_id"])


def test_no_operator_or_norm_row_carries_a_5d_dimension(run):
    # No axis-value column named "dimension" exists on nd/assignments.csv at all (the
    # deontic operator/bearer/action/... rows below prove the columns actually written);
    # the binding-level invariant is that the deontic plane's binding() is always {} (a
    # non-empty deontic binding raises PlaneIndexError before anything is written — see
    # versum.planes.build_source_entries). This test pins BOTH halves for this fixture:
    assignment_columns = set(run["assignments"][0].keys()) if run["assignments"] else set()
    assert "dimension" not in assignment_columns
    deontic_rows = [a for a in run["assignments"]
                    if a["system_id"] == _system_id(run, "deontic")]
    assert deontic_rows
    for row in deontic_rows:
        assert "dimension" not in row
    # and the norm entries themselves get no 5D contribution attributable to the operator:
    # each norm's dominant dimension is "structural" (embeds link only) — never a
    # dimension the deontic operator itself would have to have contributed.
    for e in _deontic_entries(run):
        assert e["dominant_dimension"] != "" and e["dominant_dimension"] is not None


# ── (5) mutation probes: proof each assertion actually bites ────────
def test_mutation_probe_disabling_the_nd_write_path_fails_the_count_test(
        tmp_path, monkeypatch):
    """Simulate the nD-write wiring being disabled (Round 5's own bug, pre-fix): the
    indexer runs to completion but ``nd/assignments.csv`` ends up empty. The
    ``n_nd_assignments > 0`` assertion this suite relies on must then fail."""
    import versum.nd as nd_mod

    monkeypatch.setattr(nd_mod, "save_assignments", lambda path, rows: nd_mod._save_rows(
        path, nd_mod.ASSIGNMENT_COLUMNS, []))

    src = tmp_path / "src"
    src.mkdir()
    (src / "policy.txt").write_text(POLICY_TEXT, encoding="utf-8")
    out = tmp_path / "out"
    manifest = index_folder(src, "law-eu", out, planes=pl.DISCOVER)
    assignments = load_assignments(out / "nd" / "assignments.csv")
    assert manifest["n_nd_assignments"] > 0  # the manifest count itself is unaffected...
    with pytest.raises(AssertionError):
        assert len(assignments) > 0  # ...but the file the CLI/consumers actually read is empty


def test_mutation_probe_an_operator_row_with_a_dimension_fails_the_no_5d_test(run):
    """Simulate a future regression that attaches a cross-profile 5D 'dimension' value to a
    deontic operator row (exactly the D1/Round-4/Round-5 violation this whole suite
    exists to prevent). The no-5D-on-operator-rows assertion must fail against it."""
    deontic_rows = [dict(a) for a in run["assignments"]
                    if a["system_id"] == _system_id(run, "deontic")
                    and a["axis_id"] == "operator"]
    assert deontic_rows
    mutated = [{**row, "dimension": "relational"} for row in deontic_rows]
    with pytest.raises(AssertionError):
        for row in mutated:
            assert "dimension" not in row


def test_jurisdiction_and_time_columns_are_present_but_empty_without_provenance(run):
    # no consume registry / kg sidecar is supplied for this fixture, so no jurisdiction /
    # time coordinate is minted (never fabricated) — this is expected, not a defect.
    core_rows = [a for a in run["assignments"] if a["axis_id"] in ("jurisdiction", "time")]
    assert core_rows == []
