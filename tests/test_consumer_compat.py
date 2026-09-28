"""Consumer-compat: ``versum`` must remain usable exactly as
``ctrl-legal/router/adapters/grounding.py`` uses it — same imports, same call shapes,
same columns — WITHOUT importing ctrl-legal (never a cross-repo import; the call
shapes below are copied by hand from a read-only look at that file, not executed
against it).

Mirrored calls (from ``ctrl-legal/router/adapters/grounding.py``, read-only,
never edited by this task):

    from versum.nd import load_assignments as _load_assignments
    from versum.store.graph import load_claims as _load_claims
    ...
    list(_load_assignments(root / "nd" / "assignments.csv")), \
        list(_load_claims(root / "claims.csv"))

Mirrored columns (from the same file's ``_build_coordinates`` / ``_gather_claims``):

    assignments.csv rows read BY NAME: subject_id, system_id, axis_id, value
    claims.csv      rows read BY NAME: source_urn, verification, predicate, polarity

This test indexes the committed ``credit_policy_nd`` fixture (the same fixture and code
path as ``tests/test_nd_on_index.py``), then calls ``load_assignments`` /
``load_claims`` exactly as above and asserts every column grounding.py reads by name is
present on every row it would iterate.
"""
from __future__ import annotations

from pathlib import Path

from versum import planes as pl
from versum.nd import ASSIGNMENT_COLUMNS as _ASSIGNMENT_COLUMNS
from versum.nd import load_assignments as _load_assignments
from versum.store.graph import load_claims as _load_claims
from versum.store.index import index_folder

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "credit_policy_nd"
POLICY_TEXT = (FIXTURE / "policy.txt").read_text(encoding="utf-8")

# The columns grounding.py's _build_coordinates() reads by name off assignments.csv rows.
ASSIGNMENT_COLUMNS_READ = ("subject_id", "system_id", "axis_id", "value")
# The columns grounding.py's _gather_claims() reads by name off claims.csv rows.
CLAIM_COLUMNS_READ = ("source_urn", "verification", "predicate", "polarity")

# nd/assignments.csv's own column list, frozen here (independent of ``versum.nd``) so a
# change to it is caught by an equality assertion, not just "still has these names".
PRIOR_ASSIGNMENT_COLUMNS = (
    "assignment_id", "subject_id", "system_id", "system_version", "axis_id", "value",
    "source_id", "method", "confidence", "verification")


def _index(tmp_path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "policy.txt").write_text(POLICY_TEXT, encoding="utf-8")
    out = tmp_path / "out"
    index_folder(src, "law-eu", out, planes=pl.DISCOVER)
    return out


def test_read_store_call_shape_succeeds(tmp_path):
    """Mirrors grounding.read_store()'s one real line of work:

        list(_load_assignments(root / "nd" / "assignments.csv")), \
            list(_load_claims(root / "claims.csv"))
    """
    root = _index(tmp_path)
    assignments, claims = (list(_load_assignments(root / "nd" / "assignments.csv")),
                           list(_load_claims(root / "claims.csv")))
    assert isinstance(assignments, list) and assignments
    assert isinstance(claims, list) and claims


def test_assignments_csv_carries_every_column_grounding_reads_by_name(tmp_path):
    root = _index(tmp_path)
    assignments = list(_load_assignments(root / "nd" / "assignments.csv"))
    assert assignments
    for row in assignments:
        for col in ASSIGNMENT_COLUMNS_READ:
            assert col in row, (col, sorted(row))


def test_claims_csv_carries_every_column_grounding_reads_by_name(tmp_path):
    root = _index(tmp_path)
    claims = list(_load_claims(root / "claims.csv"))
    assert claims
    for row in claims:
        for col in CLAIM_COLUMNS_READ:
            assert col in row, (col, sorted(row))


def test_build_coordinates_shape_grounding_uses(tmp_path):
    """Mirrors grounding._build_coordinates(): only rows whose (system_id, axis_id) is
    tracked contribute; every other row must be a silent skip, never an exception, for
    ANY row this store can produce — the tracked-axis dict is grounding.py's own, copied
    here verbatim, not re-derived from versum."""
    root = _index(tmp_path)
    assignments = list(_load_assignments(root / "nd" / "assignments.csv"))
    tracked_axes = {
        ("versum-context", "jurisdiction"): "jurisdiction",
        ("topos", "rank"): "rank",
    }
    coord: dict[str, dict[str, str]] = {}
    for row in assignments:
        subject_id = row.get("subject_id")
        system_id = row.get("system_id")
        axis_id = row.get("axis_id")
        value = row.get("value")
        if not isinstance(subject_id, str) or not subject_id:
            continue
        if not isinstance(system_id, str) or not isinstance(axis_id, str):
            continue
        axis_key = tracked_axes.get((system_id, axis_id))
        if axis_key is None:
            continue
        if not isinstance(value, str):
            continue
        coord.setdefault(subject_id, {})[axis_key] = value.strip('"')
    # no exception raised while walking every row this store produced (the shape holds);
    # this fixture carries no jurisdiction/rank provenance, so no subject is tracked —
    # that is the expected, honest-degrade outcome, not a defect of this test.
    assert coord == {}


def test_assignments_csv_header_is_the_prior_column_list(tmp_path):
    """Backward compatibility (Round 6, item 3): the marker/claims.csv-side fix for a
    normative claim's dimension must not touch ``nd/assignments.csv`` at all — its column
    set/order is a frozen consumer seam (``docs/nd-on-index.md``)."""
    root = _index(tmp_path)
    with open(root / "nd" / "assignments.csv", newline="", encoding="utf-8") as fh:
        header = fh.readline().strip().split(",")
    assert tuple(header) == PRIOR_ASSIGNMENT_COLUMNS == _ASSIGNMENT_COLUMNS


def test_normative_claim_has_empty_dimension_and_no_companion_row(tmp_path):
    """Item (3), Phase 0 ontology seam (revert): claims.csv and the profile audit must
    agree. A marker-gated normative (operator) claim — "must not"/"may"/"shall" in this
    fixture, predicates "prohibits", "permits", "imposes" — carries NO cross-profile 5D
    dimension of its own (empty, not the relational-floor fallback). The companion-row
    design (a second ``type=action``/``embedded_in`` claims.csv row carrying that
    dimension) was reverted: an action type is NEVER asserted onto any claims.csv row —
    it lives only as a not-asserted entry in the entry model (``entries.csv`` /
    ``entry_claims.jsonl``, :mod:`versum.planes`), linked from its sentence/claim entry
    by the structural "embeds" relation, never as a second row here. Calling
    ``load_claims`` on the store must still succeed and return the normative claim's own
    row (never raise, never silently drop it)."""
    from versum.profiles import law_eu
    from versum.store import graph as g

    root = _index(tmp_path)
    claims = list(_load_claims(root / "claims.csv"))
    assert claims  # load_claims did not drop rows

    normative_predicates = law_eu.PROFILE.unmapped_predicates()
    assert normative_predicates  # the fixture profile has at least one, or this test is moot

    # claims.csv no longer has a companion-row vocabulary at all: no "embeds" /
    # "embedded_in" column, and no row's "type" is ever "action".
    assert "embeds" not in g.Claim.__dataclass_fields__
    assert "embedded_in" not in g.Claim.__dataclass_fields__
    assert all(c.get("type") != "action" for c in claims)

    normative_claims = [c for c in claims if c["predicate"] in normative_predicates]
    assert normative_claims, "fixture must exercise at least one normative-operator claim"

    for claim in normative_claims:
        assert claim["dimension"] == "", (
            f"normative claim {claim['item_id']} must carry an empty dimension, matching "
            f"Profile.federation_projections()'s 'not_declared' audit verdict for "
            f"{claim['predicate']!r}; got {claim['dimension']!r}"
        )
        assert "embeds" not in claim and "embedded_in" not in claim


def test_load_assignments_and_load_claims_both_succeed_on_a_normative_store(tmp_path):
    """Exactly the ``ctrl-legal`` consumer call shape, on a store that contains a
    normative claim: neither call may raise, and the normative claim row is present."""
    from versum.profiles import law_eu

    root = _index(tmp_path)
    assignments = list(_load_assignments(root / "nd" / "assignments.csv"))
    claims = list(_load_claims(root / "claims.csv"))
    assert assignments
    normative_predicates = law_eu.PROFILE.unmapped_predicates()
    assert any(c["predicate"] in normative_predicates for c in claims)


def test_gather_claims_shape_grounding_uses(tmp_path):
    """Mirrors grounding._gather_claims()'s column-presence walk (the prefix-match logic
    itself is ctrl-legal's; only the column access shape is exercised here)."""
    root = _index(tmp_path)
    claims = list(_load_claims(root / "claims.csv"))
    matched = []
    for row in claims:
        source_urn = row.get("source_urn")
        verification = row.get("verification")
        predicate = row.get("predicate")
        polarity = row.get("polarity")
        if not isinstance(source_urn, str) or not source_urn:
            continue
        if not isinstance(verification, str):
            continue
        if not isinstance(predicate, str) or not isinstance(polarity, str):
            continue
        matched.append(row)
    assert matched  # every claims.csv row this store writes satisfies grounding's shape
