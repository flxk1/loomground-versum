"""Phase 0 ontology seam, item (1): claims.csv write boundary.

A norm's action type/content must never reach ``claims.csv`` under any verification or
column shape (the reverted companion-row design did exactly this, tagging the row
``verification="structural"``). ``versum.store.graph.save_claims`` enforces this
directly: :class:`versum.store.graph.ClaimProvenanceError` raises for any row lacking an
asserted provenance chain (a recognised ``verification`` plus ``source_urn`` and a span)
before anything is written.

This file proves, without editing ``src/``:
  * the writer raises on an unprovenanced row (a row shaped like the reverted companion
    row, ``verification="structural"``);
  * indexing the committed ``credit_case`` fixture never produces a claims.csv row that
    is action-type/norm content (no row typed ``"action"``, no ``embeds``/``embedded_in``
    column at all);
  * a lint-style scan (source text + a light AST walk) that fails if any code path other
    than the guarded ``save_claims`` ever writes to a file named ``claims.csv`` under
    ``versum.store.index`` (the single-folder ``.versum/`` store this Phase 0 seam
    governs). ``versum.sync.KGStore`` maintains a SEPARATE, pre-existing, by-domain
    aggregate store (``by-domain/<domain>/claims.csv``) that this Phase 0 task does not
    touch or govern -- noted, not asserted about, here.
"""
from __future__ import annotations

import ast
import csv
from pathlib import Path

import pytest

from versum.store import graph as g
from versum.store.index import index_folder

REPO_SRC = Path(__file__).resolve().parents[1] / "src"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "credit_case"
POLICY = FIXTURE / "policy.txt"


def _rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ── (1a) the writer raises on a row without asserted provenance ────────
def test_save_claims_raises_on_a_row_without_asserted_provenance(tmp_path):
    """Exactly the reverted companion row's shape: verification='structural'."""
    bad_row = {
        "item_id": "action-fake0000000000",
        "source_urn": "urn:test:fixture",
        "span_start": 0,
        "span_end": 10,
        "type": "action",
        "predicate": "prohibits",
        "dimension": "relational",
        "verification": "structural",
        "embedded_in": "item-does-not-matter",
    }
    with pytest.raises(g.ClaimProvenanceError):
        g.save_claims(tmp_path / "claims.csv", [bad_row], "law-eu")
    assert not (tmp_path / "claims.csv").exists(), (
        "a rejected row must leave nothing written")


def test_save_claims_raises_on_missing_source_urn():
    row = {"item_id": "x", "source_urn": "", "span_start": 0, "span_end": 1,
          "verification": "candidate"}
    with pytest.raises(g.ClaimProvenanceError):
        g._check_claim_provenance(row)


def test_save_claims_raises_on_missing_span():
    row = {"item_id": "x", "source_urn": "urn:test:fixture", "span_start": None,
          "span_end": None, "verification": "candidate"}
    with pytest.raises(g.ClaimProvenanceError):
        g._check_claim_provenance(row)


def test_save_claims_accepts_an_asserted_row(tmp_path):
    good_row = {"item_id": "item-fake0000000000", "source_urn": "urn:test:fixture",
               "span_start": 0, "span_end": 10, "type": "is", "predicate": "prohibits",
               "dimension": "", "verification": "candidate", "text": "x" * 10}
    g.save_claims(tmp_path / "claims.csv", [good_row], "law-eu")
    rows = _rows(tmp_path / "claims.csv")
    assert len(rows) == 1 and rows[0]["item_id"] == "item-fake0000000000"


# ── (1b) indexing the credit fixture never asserts norm content on claims.csv ──
@pytest.fixture(scope="module")
def indexed_credit_case(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("write_boundary")
    src = root / "src"
    src.mkdir()
    import shutil
    shutil.copyfile(POLICY, src / "policy.txt")
    out = root / "out"
    index_folder(src, "law-eu", out)
    return out


def test_no_claims_row_is_action_type_or_norm_content(indexed_credit_case):
    claims = _rows(indexed_credit_case / "claims.csv")
    assert claims, "the fixture must exercise at least one candidate claim"
    for row in claims:
        assert row.get("type") != "action", (
            f"claims.csv row {row.get('item_id')} is typed 'action' -- norm content "
            "reached claims.csv, which the Phase 0 write boundary forbids")
        assert "embeds" not in row and "embedded_in" not in row, (
            "the reverted companion-row column vocabulary must not reappear")
        # a normative (operator) claim carries an empty dimension; nothing on this
        # store's claims.csv ever carries the companion verification marker.
        assert row.get("verification") != "structural"


def test_claim_dataclass_has_no_companion_row_columns():
    fields = set(g.Claim.__dataclass_fields__)
    assert "embeds" not in fields and "embedded_in" not in fields


# ── (1c) lint-style scan: only save_claims ever writes claims.csv here ──
def test_only_save_claims_writes_claims_csv_in_the_index_module():
    """AST walk of ``versum.store.index``: the only reference to a file literally named
    ``claims.csv`` is the doc/manifest comment and the ONE guarded call site,
    ``g.save_claims(out / "claims.csv", ...)``. No other function in this module opens,
    writes, or otherwise persists to a path built from the literal ``"claims.csv"``."""
    index_src = (REPO_SRC / "versum" / "store" / "index.py").read_text(encoding="utf-8")
    tree = ast.parse(index_src)

    call_sites: list[ast.Call] = []

    class _Walker(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            dump = ast.dump(node)
            if "claims.csv" in dump:
                call_sites.append(node)
            self.generic_visit(node)

    _Walker().visit(tree)
    assert call_sites, "expected at least the guarded save_claims call site"
    for node in call_sites:
        assert isinstance(node.func, ast.Attribute) and node.func.attr == "save_claims", (
            "a call site touching 'claims.csv' outside the guarded save_claims() call "
            f"was found: {ast.dump(node)[:200]}")


def test_save_claims_is_the_only_writer_of_the_claim_dataclass_shape():
    """AST walk of ``versum.store.graph``: only ``save_claims`` calls ``_write_csv`` with
    the module-level ``Claim`` dataclass' own field shape (i.e. the claims.csv writer).
    Every other ``_write_csv`` call site in this module targets a different, non-claim
    column list (``CONCEPT_COLUMNS`` / ``EDGE_COLUMNS``)."""
    graph_src = (REPO_SRC / "versum" / "store" / "graph.py").read_text(encoding="utf-8")
    tree = ast.parse(graph_src)

    class _FuncWalker(ast.NodeVisitor):
        def __init__(self):
            self.writers_of_claim_columns: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            attrs = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            calls_write_csv = "_write_csv" in names
            touches_claim_shape = "Claim" in names or "keys" in attrs
            if calls_write_csv and touches_claim_shape:
                self.writers_of_claim_columns.append(node.name)
            self.generic_visit(node)

    walker = _FuncWalker()
    walker.visit(tree)
    assert walker.writers_of_claim_columns == ["save_claims"], (
        "exactly one function may build claims.csv's own column shape and write it: "
        f"found {walker.writers_of_claim_columns!r}")


# ── mutation harness note ───────────────────────────────────────────
# The write-boundary mutation run (disabling the ``_check_claim_provenance`` guard on a
# scratch copy of this repo, never in-tree) and its failing node id are reported by the
# calling task, not executed as part of the committed suite -- see the task report.
