"""Phase 8 end-to-end acceptance: the credit-decision case (PORT-PLAN draft 4).

``versum index`` is run as a CLI subprocess with no plane flag at all, so the only way a
plane takes part is entry-point discovery (``loomground.planes``) of the installed plane
packages. Every output lands in pytest's ``tmp_path``, never in the repository.

What each test proves (plan fit rules in brackets):

* per-sentence rows s1..s7 of the acceptance table;
* invariants: A4 (every sentence yields an entry), exact spans into the unmodified
  source, a five-value 5D position with exactly one dominant dimension, links typed by
  one of the five dimensions [rule 3], versioned provenance on every assignment
  [rule 5], source-level jurisdiction/time on every entry;
* single source [rule 1]: versions and system ids are read from the installed planes,
  never restated here;
* round-trip [rule 4]: every installed plane's published examples, projected into the
  versum and read back, reproduce ``produce()`` field for field;
* topos coordinates present iff source metadata supplies them;
* fail-closed [rule 6]: an out-of-vocabulary value aborts the run, non-zero, and nothing
  is written.

No plane vocabulary is asserted beyond the acceptance table's own words.
"""
from __future__ import annotations

import copy
import csv
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from versum import planes as pl
from versum import position5d as p5
from versum.nd import load_assignments, load_bindings

REPO = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "credit_case"
POLICY = FIXTURE / "policy.txt"
SIDECAR = FIXTURE / "policy.txt.metadata.json"

POLICY_TEXT = (
    "The bank is a controller. "
    "The scoring model is part of the credit system. "
    "The controller must not make a solely automated decision on a credit application. "
    "The controller may use the score to prepare a decision. "
    "The controller knows that the training data is inaccurate. "
    "A reviewer shall examine every rejection before it is sent. "
    "The review follows the automated scoring."
)
SENTENCES = [s if s.endswith(".") else s + "." for s in POLICY_TEXT.split(". ")]

PLANE_EPS = sorted(importlib.metadata.entry_points(group=pl.ENTRY_POINT_GROUP),
                   key=lambda e: e.name)
PLANE_IDS = [e.name for e in PLANE_EPS]
EXPECTED_PLANES = ["deontic", "epistemic", "factual", "governance", "topos"]


# ── helpers ───────────────────────────────────────────────────────
def _rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _raw_descriptor(name: str) -> dict:
    """The installed plane's own descriptor, unvalidated (to read its published id and
    version even when the descriptor breaks the contract)."""
    (ep,) = [e for e in PLANE_EPS if e.name == name]
    return ep.load()()


def _installed_versions() -> dict[str, tuple[str, str]]:
    """system_id -> (plane id, language_version), from the installed planes [rule 1]."""
    out = {}
    for name in PLANE_IDS:
        raw = _raw_descriptor(name)
        out[raw["nd_system"]["id"]] = (name, raw["language_version"])
    return out


def _cli_env() -> dict:
    # No PYTHONPATH at all: the child is this venv's interpreter, so versum and every
    # plane resolve only through what is installed in the venv (editable installs and
    # their dist-info entry points). A plane that is not installed cannot sneak in.
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return env


def _run_index(src: Path, out: Path) -> subprocess.CompletedProcess:
    """``versum index <src> --out <out>`` with NO plane flag: discovery only."""
    assert REPO not in out.resolve().parents, "index output must stay out of the repo"
    return subprocess.run(
        [sys.executable, "-m", "versum", "index", str(src), "--out", str(out)],
        cwd=str(src.parent), env=_cli_env(), capture_output=True, text=True, timeout=300)


def _stage(root: Path, sidecar: dict | None = None) -> Path:
    src = root / "src"
    src.mkdir(parents=True)
    shutil.copyfile(POLICY, src / "policy.txt")
    side = json.loads(SIDECAR.read_text(encoding="utf-8")) if sidecar is None else sidecar
    (src / SIDECAR.name).write_text(json.dumps(side, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    return src


class Index:
    """The files of one ``versum index`` run, read back."""

    def __init__(self, src: Path, out: Path, proc: subprocess.CompletedProcess):
        self.src, self.out, self.proc = src, out, proc

    def ok(self) -> "Index":
        assert self.proc.returncode == 0, (
            f"`versum index` (no plane flags) exited {self.proc.returncode}\n"
            f"stderr: {self.proc.stderr.strip()[-2000:]}")
        return self

    @property
    def source_text(self) -> str:
        return (self.src / "policy.txt").read_bytes().decode("utf-8")

    @property
    def manifest(self) -> dict:
        return json.loads((self.out / "index.json").read_text(encoding="utf-8"))

    @property
    def entries(self) -> list[dict]:
        return _rows(self.out / "entries.csv")

    @property
    def links(self) -> list[dict]:
        return _rows(self.out / "entry_links.csv")

    @property
    def claims(self) -> list[dict]:
        return [json.loads(x) for x in
                (self.out / "entry_claims.jsonl").read_text(encoding="utf-8").splitlines()]

    @property
    def assignments(self) -> list[dict]:
        return load_assignments(self.out / "nd" / "assignments.csv")

    @property
    def bindings(self) -> list[dict]:
        return load_bindings(self.out / "nd" / "bindings.csv")

    def coords(self, item_id: str, system_id: str) -> dict:
        out: dict = {}
        for a in self.assignments:
            if a["subject_id"] == item_id and a["system_id"] == system_id:
                out.setdefault(a["axis_id"], []).append(a["value"])
        return {k: v[0] if len(v) == 1 else sorted(v, key=json.dumps)
                for k, v in out.items()}

    def entry_claims(self, item_id: str, plane: str) -> list[dict]:
        return [c["claim"] for c in self.claims
                if c["item_id"] == item_id and c["plane"] == plane]

    def sentence_entries(self, idx: int) -> list[dict]:
        return [e for e in self.entries if int(e["sentence_index"]) == idx]

    def find(self, idx: int, plane: str, relation: str | None = None) -> dict:
        """The one entry of sentence ``idx`` that ``plane`` claims (with ``relation``)."""
        hits = [e for e in self.sentence_entries(idx)
                if any(r.split(":", 1)[0] == plane
                       and (relation is None or r.split(":", 1)[1] == relation)
                       for r in e["relations"].split(";") if r)]
        assert len(hits) == 1, (
            f"sentence {idx} ({SENTENCES[idx]!r}): expected one {plane}"
            f"{':' + relation if relation else ''} entry, got "
            f"{[(e['span_start'], e['span_end'], e['relations']) for e in hits]}")
        return hits[0]


def _system_id(plane: str) -> str:
    return _raw_descriptor(plane)["nd_system"]["id"]


@pytest.fixture(scope="module")
def run(tmp_path_factory) -> Index:
    root = tmp_path_factory.mktemp("credit_case")
    src = _stage(root)
    out = root / "out"
    return Index(src, out, _run_index(src, out))


# ── fixture and invocation ────────────────────────────────────────
def test_fixture_is_the_seven_sentence_text():
    assert POLICY.read_bytes() == POLICY_TEXT.encode("utf-8")
    assert len(SENTENCES) == 7
    side = json.loads(SIDECAR.read_text(encoding="utf-8"))
    assert side["jurisdiction"] == ["EU", "DE"] and side["canonical_urn"]


def test_the_five_planes_are_discovered_through_the_venv():
    assert PLANE_IDS == EXPECTED_PLANES
    for ep in PLANE_EPS:
        assert ep.dist is not None, ep  # published by an installed distribution
        raw = _raw_descriptor(ep.name)
        assert raw["nd_system"]["id"] and raw["language_version"], ep.name


def test_index_runs_with_discovery_only_and_writes_outside_the_repo(run):
    run.ok()
    assert "PYTHONPATH" not in _cli_env()
    assert REPO not in run.out.resolve().parents
    m = run.manifest
    assert [p["plane"] for p in m["planes"]] == PLANE_IDS  # every installed plane, found
    assert m["n_sources"] == 1
    (source,) = _rows(run.out / "sources.csv")
    assert source["source_urn"] == json.loads(SIDECAR.read_text())["canonical_urn"]


# ── invariants ────────────────────────────────────────────────────
def test_every_sentence_yields_an_entry_whose_span_slices_the_source(run):
    run.ok()
    raw = POLICY.read_bytes().decode("utf-8")  # the fixture bytes, not a cleaned copy
    text = run.source_text
    assert text == raw == POLICY_TEXT
    entries = run.entries
    for idx, sentence in enumerate(SENTENCES):
        own = [e for e in entries if int(e["sentence_index"]) == idx]
        assert own, f"A4: sentence {idx} has no entry"
        (sent,) = [e for e in own if e["entry_kind"] == "sentence"]
        assert raw[int(sent["span_start"]):int(sent["span_end"])] == sentence
        for e in own:
            assert raw[int(e["span_start"]):int(e["span_end"])] == e["text"], e["item_id"]
    for e in entries:
        s, t = int(e["span_start"]), int(e["span_end"])
        assert 0 <= s < t <= len(text)
        assert raw[s:t] == e["text"], e["item_id"]  # the stored text is the exact slice
        assert text[s:t].strip() == text[s:t] and text[s:t]
        assert e["item_id"] == pl.entry_id(e["source_urn"], s, t)
        if e["entry_kind"] == "embedded":
            parent = next(p for p in entries if p["item_id"] == e["parent_id"])
            assert int(parent["span_start"]) <= s and t <= int(parent["span_end"])


def test_every_entry_has_a_five_value_position_and_one_dominant_dimension(run):
    run.ok()
    for e in run.entries:
        pos = {d: float(e[d]) for d in p5.DIMENSIONS}
        assert len(pos) == 5 and all(0.0 <= v <= 1.0 for v in pos.values())
        assert e["dominant_dimension"] in p5.DIMENSIONS  # a single value, never a list
        if e["position_basis"] == p5.BASIS_PLANES:
            assert abs(sum(pos.values()) - 1.0) < 1e-5
            assert pos[e["dominant_dimension"]] == max(pos.values())
        else:
            assert e["position_basis"] == p5.BASIS_DEFAULT
            assert sum(pos.values()) == 0.0
            assert e["dominant_dimension"] == p5.NO_PLANE_DOMINANT


def test_links_are_typed_by_one_of_the_five_dimensions(run):
    run.ok()
    ids = {e["item_id"] for e in run.entries}
    assert run.links
    for link in run.links:
        assert link["dimension"] in p5.DIMENSIONS
        assert link["src_id"] in ids and link["dst_id"] in ids and link["relation"]


def test_every_assignment_names_system_version_and_provenance(run):
    run.ok()
    installed = _installed_versions()
    systems = json.loads((run.out / "nd" / "systems.json").read_text())
    registered = json.dumps(systems)
    urn = json.loads(SIDECAR.read_text())["canonical_urn"]
    plane_rows = [a for a in run.assignments if a["system_id"] in installed]
    assert plane_rows
    for a in run.assignments:
        assert a["system_id"] and a["system_version"] and a["method"] and a["source_id"]
        if a["system_id"] in installed:
            plane, version = installed[a["system_id"]]
            assert a["system_version"] == version, (plane, a)  # rule 5: version-locked
            assert a["source_id"] == urn
            assert a["subject_id"].startswith("ent-")
    for plane, version in installed.values():
        assert version in registered
    for c in run.claims:
        assert installed[_system_id(c["plane"])][1] == c["language_version"]


def test_jurisdiction_and_time_apply_to_every_entry(run):
    run.ok()
    urn = json.loads(SIDECAR.read_text())["canonical_urn"]
    assignments = run.assignments
    for e in run.entries:
        coords = pl.entry_coordinates(e, assignments)
        jur = {c["value"] for c in coords if c["axis_id"] == "jurisdiction"}
        time = {json.dumps(c["value"]) for c in coords if c["axis_id"] == "time"}
        assert jur == {"EU", "DE"}, e["item_id"]
        assert time == {json.dumps("2026")}, e["item_id"]
    core = [a for a in assignments if a["axis_id"] in ("jurisdiction", "time")]
    assert core and all(a["subject_id"] == urn for a in core)


# ── the acceptance table, sentence by sentence ────────────────────
def test_s1_bank_is_a_controller_structural_factual(run):
    run.ok()
    e = run.find(0, "factual", "is-a")
    assert e["dominant_dimension"] == "structural"
    c = run.coords(e["item_id"], _system_id("factual"))
    assert (c["subject"], c["predicate"], c["object"]) == ("bank", "is", "controller")


def test_s2_part_of_is_kept_structural_factual(run):
    run.ok()
    e = run.find(1, "factual", "part-of")
    assert e["dominant_dimension"] == "structural"
    c = run.coords(e["item_id"], _system_id("factual"))
    assert (c["subject"], c["predicate"], c["object"]) == (
        "scoring model", "part of", "credit system")


def _content_entry(idx: "Index", norm_item_id: str, text: str) -> dict:
    """The one entry, parented directly by the norm's own entry, whose text is exactly
    ``text`` — the content entry a norm's ``spans.content`` was lowered into (never the
    factual plane's own, independent overlapping reading of the same sentence, which is
    also parented there for some of these sentences but never carries this exact text)."""
    hits = [e for e in idx.entries if e["parent_id"] == norm_item_id and e["text"] == text]
    assert len(hits) == 1, (norm_item_id, text,
                            [(h["span_start"], h["span_end"]) for h in hits])
    return hits[0]


def _embeds(idx: "Index", src_id: str, dst_id: str) -> None:
    hits = [l for l in idx.links if l["src_id"] == src_id and l["dst_id"] == dst_id
            and l["relation"] == "embeds" and l["dimension"] == "structural"]
    assert len(hits) == 1, (src_id, dst_id)


def _assert_action_type(idx: "Index", norm_item_id: str, content: dict, *,
                        subject: str, predicate: str, obj: str) -> None:
    """Round 5 (action-type entry): the norm's regulated action/state is entered as its
    OWN action-type entry — never asserted as the norm itself — lowered through the
    factual plane from the deontic producer's ``spans.content`` sub-span (``raw[s:e] ==
    text``, already proven by the caller). This asserts the full action-type shape the
    acceptance table promises: its s/p/o, that it is unasserted, its dimension and
    position (both already pinned by the caller just above/below this call), the
    structural 'embeds' link from the norm (also already asserted by the caller via
    :func:`_embeds`), and that the norm's own deontic ``action`` coordinate is no longer
    the literal text a second time but a concept reference to this very entry — its
    ``item_id``."""
    (fclaim,) = idx.entry_claims(content["item_id"], "factual")
    assert fclaim["asserted"] is False
    assert fclaim["entry_kind"] == "action_type"
    assert fclaim["coordinates"]["subject"] == subject
    assert fclaim["coordinates"]["predicate"] == predicate
    assert fclaim["coordinates"]["object"] == obj
    norm_action = idx.coords(norm_item_id, _system_id("deontic"))["action"]
    assert norm_action == content["item_id"], (
        "the norm's `action` axis must reference the action-type entry (its item_id / "
        "concept reference), never restate the literal action text")


def test_s3_s4_s6_action_types_are_never_asserted_as_the_norm(run):
    """Round 5, all three norms at once: every action-type entry the acceptance table
    names is unasserted (``asserted: False``, ``entry_kind: "action_type"``) and every
    norm's own ``action`` coordinate points at it, never restating its text. The
    per-sentence tests below pin each action type's s/p/o, dimension, position and embeds
    link individually; this test pins the cross-cutting invariant once, for all three."""
    run.ok()
    s3 = run.find(2, "deontic")
    s3_content = _content_entry(
        run, s3["item_id"], "make a solely automated decision on a credit application")
    _assert_action_type(run, s3["item_id"], s3_content, subject="controller",
                        predicate="make",
                        obj="solely automated decision on a credit application")
    s4 = run.find(3, "deontic")
    s4_content = _content_entry(run, s4["item_id"], "use the score to prepare a decision")
    _assert_action_type(run, s4["item_id"], s4_content, subject="controller",
                        predicate="use", obj="score to prepare a decision")
    s6 = run.find(5, "deontic")
    s6_content = _content_entry(run, s6["item_id"], "examine every rejection")
    _assert_action_type(run, s6["item_id"], s6_content, subject="reviewer",
                        predicate="examine", obj="every rejection")


def test_s3_prohibition_on_controller_with_decide_gate_reserved_and_embedded_content(run):
    run.ok()
    e = run.find(2, "deontic")
    c = run.coords(e["item_id"], _system_id("deontic"))
    assert (c["operator"], c["bearer"]) == ("F", "controller")
    # governance binding on the same entry: the `decide` gate, verdict reserved (unchanged)
    (gov,) = run.entry_claims(e["item_id"], "governance")
    assert gov["gate"] == "decide"
    g = run.coords(e["item_id"], _system_id("governance"))
    assert g["verdict"] == "reserved"
    assert [b for b in run.bindings if b["claim_id"] == e["item_id"]
            and b["assignment_id"] in {a["assignment_id"] for a in run.assignments
                                       if a["system_id"] == _system_id("governance")}]
    # Round 4 (D1 correction): the operator "F" binds to no 5D dimension (the deontic
    # plane's own binding() is always {}); the norm entry's 5D position now comes only
    # from the governance claim on the same entry (relation "reservation" -> intentional)
    # and from the structural "embeds" link to its own content entry (below) — never from
    # the operator. Pinned literal computed values:
    assert e["dominant_dimension"] == "structural"
    npos = {d: float(e[d]) for d in p5.DIMENSIONS}
    assert npos == {"structural": 0.666667, "causal": 0.0, "intentional": 0.333333,
                    "temporal": 0.0, "relational": 0.0}
    # the content entry: a sub-span of the norm sentence, raw[s:e] == text, lowered
    # through the factual plane with context['subject'] = the norm's bearer ("controller")
    content_text = "make a solely automated decision on a credit application"
    content = _content_entry(run, e["item_id"], content_text)
    assert run.source_text[int(content["span_start"]):int(content["span_end"])] == \
        content_text
    _embeds(run, e["item_id"], content["item_id"])
    fc = run.coords(content["item_id"], _system_id("factual"))
    assert (fc["subject"], fc["predicate"], fc["object"]) == (
        "controller", "make", "solely automated decision on a credit application")
    assert content["dominant_dimension"] == "relational"
    cpos = {d: float(content[d]) for d in p5.DIMENSIONS}
    assert cpos == {"structural": 0.0, "causal": 0.0, "intentional": 0.0, "temporal": 0.0,
                    "relational": 1.0}
    # Round 5: the content entry is its own action-type entry (never asserted as the
    # norm), and the norm's own `action` coordinate is a reference to it, not its text.
    (fclaim,) = run.entry_claims(content["item_id"], "factual")
    assert fclaim["asserted"] is False and fclaim["entry_kind"] == "action_type"
    assert c["action"] == content["item_id"]


def test_s4_permission_on_controller_with_embedded_content(run):
    run.ok()
    e = run.find(3, "deontic")
    c = run.coords(e["item_id"], _system_id("deontic"))
    assert (c["operator"], c["bearer"]) == ("P", "controller")
    # Round 4 (D1 correction): the operator "P" binds to no 5D dimension. No other plane
    # claims this sentence, so the norm entry's only 5D contribution is the structural
    # "embeds" link to its own content entry.
    assert e["dominant_dimension"] == "structural"
    npos = {d: float(e[d]) for d in p5.DIMENSIONS}
    assert npos == {"structural": 1.0, "causal": 0.0, "intentional": 0.0, "temporal": 0.0,
                    "relational": 0.0}
    content_text = "use the score to prepare a decision"
    content = _content_entry(run, e["item_id"], content_text)
    assert run.source_text[int(content["span_start"]):int(content["span_end"])] == \
        content_text
    _embeds(run, e["item_id"], content["item_id"])
    fc = run.coords(content["item_id"], _system_id("factual"))
    assert (fc["subject"], fc["predicate"], fc["object"]) == (
        "controller", "use", "score to prepare a decision")
    assert content["dominant_dimension"] == "relational"
    cpos = {d: float(content[d]) for d in p5.DIMENSIONS}
    assert cpos == {"structural": 0.0, "causal": 0.0, "intentional": 0.0, "temporal": 0.0,
                    "relational": 1.0}
    # Round 5: the content entry is its own action-type entry (never asserted as the
    # norm), and the norm's own `action` coordinate is a reference to it, not its text.
    (fclaim,) = run.entry_claims(content["item_id"], "factual")
    assert fclaim["asserted"] is False and fclaim["entry_kind"] == "action_type"
    assert c["action"] == content["item_id"]


def test_s5_knowledge_attitude_and_embedded_fact_are_linked_entries(run):
    run.ok()
    att = run.find(4, "epistemic")
    c = run.coords(att["item_id"], _system_id("epistemic"))
    assert (c["operator"], c["holder"], c["certainty"]) == ("K", "controller", "certain")
    fact = run.find(4, "factual")
    assert fact["item_id"] != att["item_id"] and fact["entry_kind"] == "embedded"
    f = run.coords(fact["item_id"], _system_id("factual"))
    assert (f["subject"], f["predicate"], f["object"]) == (
        "training data", "is", "inaccurate")
    assert run.source_text[int(fact["span_start"]):int(fact["span_end"])] == \
        "the training data is inaccurate"
    typed = [l for l in run.links
             if l["src_id"] == att["item_id"] and l["dst_id"] == fact["item_id"]
             and l["plane"] == "epistemic"]
    assert typed and all(l["dimension"] in p5.DIMENSIONS for l in typed)
    assert fact["parent_id"] == att["item_id"]


def test_s6_obligation_on_reviewer_with_embedded_content(run):
    run.ok()
    e = run.find(5, "deontic")
    c = run.coords(e["item_id"], _system_id("deontic"))
    assert (c["operator"], c["bearer"]) == ("O", "reviewer")
    assert c["condition"] == "before it is sent"  # the condition stays on the norm entry
    # Round 4 (D1 correction): the operator "O" binds to no 5D dimension. No other plane
    # claims this sentence, so the norm entry's only 5D contribution is the structural
    # "embeds" link to its own content entry.
    assert e["dominant_dimension"] == "structural"
    npos = {d: float(e[d]) for d in p5.DIMENSIONS}
    assert npos == {"structural": 1.0, "causal": 0.0, "intentional": 0.0, "temporal": 0.0,
                    "relational": 0.0}
    content_text = "examine every rejection"
    content = _content_entry(run, e["item_id"], content_text)
    assert run.source_text[int(content["span_start"]):int(content["span_end"])] == \
        content_text
    _embeds(run, e["item_id"], content["item_id"])
    fc = run.coords(content["item_id"], _system_id("factual"))
    assert (fc["subject"], fc["predicate"], fc["object"]) == (
        "reviewer", "examine", "every rejection")
    assert content["dominant_dimension"] == "relational"
    cpos = {d: float(content[d]) for d in p5.DIMENSIONS}
    assert cpos == {"structural": 0.0, "causal": 0.0, "intentional": 0.0, "temporal": 0.0,
                    "relational": 1.0}
    # Round 5: the content entry is its own action-type entry (never asserted as the
    # norm), and the norm's own `action` coordinate is a reference to it, not its text.
    (fclaim,) = run.entry_claims(content["item_id"], "factual")
    assert fclaim["asserted"] is False and fclaim["entry_kind"] == "action_type"
    assert c["action"] == content["item_id"]


def test_s7_ordering_is_temporal_automated_scoring_precedes_review(run):
    run.ok()
    e = run.find(6, "factual", "precedes")
    assert e["dominant_dimension"] == "temporal"
    c = run.coords(e["item_id"], _system_id("factual"))
    assert (c["subject"], c["predicate"], c["object"]) == (
        "automated scoring", "precedes", "review")


# ── topos: present iff the source metadata supplies it ────────────
def test_topos_absent_when_the_sidecar_supplies_no_topos_metadata(run):
    run.ok()
    axes = _raw_descriptor("topos")["nd_system"]["axes"]
    assert not set(axes) & set(json.loads(SIDECAR.read_text()))
    assert not [a for a in run.assignments if a["system_id"] == _system_id("topos")]


# Illustrative, generic source-level topos metadata for the fixture (not grounded data).
TOPOS_SIDECAR = {
    "rank": "regulation",
    "level": "eu",
    "organ": "eu:parliament-and-council",
    "competence": ["data-protection"],
    "scope": ["automated-decision"],
    "reception": "monist",
}
# The coordinates every sentence entry must carry, written out independently of the sidecar above.
TOPOS_EXPECTED = {
    ("rank", "regulation"),
    ("level", "eu"),
    ("organ", "eu:parliament-and-council"),
    ("competence", "data-protection"),
    ("scope", "automated-decision"),
    ("reception", "monist"),
}


def test_topos_present_when_the_sidecar_supplies_topos_metadata(tmp_path):
    side = {**json.loads(SIDECAR.read_text()), **TOPOS_SIDECAR}
    src = _stage(tmp_path, side)
    idx = Index(src, tmp_path / "out", _run_index(src, tmp_path / "out")).ok()
    topos = _system_id("topos")
    rows = [a for a in idx.assignments if a["system_id"] == topos]
    assert rows, "sidecar supplies topos metadata but no topos coordinate was written"
    sentence_ids = {e["item_id"] for e in idx.entries if e["entry_kind"] == "sentence"}
    assert len(sentence_ids) == 7
    assert {a["subject_id"] for a in rows} == sentence_ids
    for sid in sentence_ids:
        got = {(a["axis_id"], a["value"]) for a in rows if a["subject_id"] == sid}
        assert got == TOPOS_EXPECTED, (sid, got)


# ── rule 4: published examples round-trip field for field ─────────
@pytest.mark.parametrize("plane_id", PLANE_IDS)
def test_published_examples_round_trip_through_the_versum(plane_id, tmp_path):
    from versum.store.index import index_folder

    plane = pl.DescriptorPlane.from_descriptor(_raw_descriptor(plane_id),
                                               entry_name=plane_id)
    system = plane.nd_system()
    examples = plane.examples()
    for i, ex in enumerate(examples):
        sentence, context = ex["sentence"], ex.get("context")
        produced = plane.produce(sentence, copy.deepcopy(context))
        if "expected" in ex:
            assert ex["expected"] == produced, (plane_id, sentence)
        folder = tmp_path / f"ex{i:03d}"
        folder.mkdir()
        urn = f"urn:acceptance:{plane_id}:{i}"
        if context is None:
            (folder / "example.txt").write_text(sentence, encoding="utf-8")
            index_folder(folder, "generic", out=folder / "out", planes=[plane])
            claims = [json.loads(x) for x in (folder / "out" / "entry_claims.jsonl")
                      .read_text(encoding="utf-8").splitlines()]
            assignments = load_assignments(folder / "out" / "nd" / "assignments.csv")
        else:
            built = pl.build_source_entries(sentence, urn, [plane], context=context)
            claims = json.loads(json.dumps(built.claims, ensure_ascii=False))
            assignments = [json.loads(json.dumps(a.__dict__)) for a in built.assignments]
        assert [c["claim"] for c in claims] == json.loads(json.dumps(produced)), \
            (plane_id, sentence)
        for c in claims:
            assert c["plane"] == plane_id
            assert c["language_version"] == plane.language_version
            got: dict = {}
            for a in assignments:
                if a["subject_id"] == c["item_id"] and a["system_id"] == system.system_id:
                    assert a["system_version"] == plane.language_version
                    got.setdefault(a["axis_id"], set()).add(json.dumps(a["value"]))
            for axis, value in c["claim"].get("coordinates", {}).items():
                values = value if (isinstance(value, list)
                                   and system.axes[axis].cardinality == "many"
                                   and system.axes[axis].value_type != "interval") \
                    else [value]
                assert {json.dumps(v) for v in values} <= got.get(axis, set()), \
                    (plane_id, sentence, axis)


# ── rule 6: fail closed on an out-of-vocabulary value ─────────────
OOV_OPERATOR = "not-an-operator"
_REAL_DEONTIC = [e for e in PLANE_EPS if e.name == "deontic"]


def _oov_deontic_plane() -> dict:
    """A fake descriptor: the real deontic plane, with its producer wrapped so that every
    operator it emits is replaced by an out-of-vocabulary value. No plane is edited."""
    raw = _REAL_DEONTIC[0].load()()
    real = raw["produce"]

    def produce(sentence, context=None):
        claims = copy.deepcopy(real(sentence, context))
        for claim in claims:
            if "operator" in claim.get("coordinates", {}):
                claim["coordinates"]["operator"] = OOV_OPERATOR
        return claims

    return {**raw, "produce": produce}


def test_out_of_vocabulary_value_fails_closed_and_writes_nothing(tmp_path, monkeypatch,
                                                                 capsys):
    from versum.__main__ import main

    assert _REAL_DEONTIC, "the deontic plane is not installed"
    assert OOV_OPERATOR not in json.dumps(
        _raw_descriptor("deontic")["nd_system"]["axes"]["operator"])
    fake = importlib.metadata.EntryPoint(
        name="deontic", value=f"{__name__}:_oov_deontic_plane",
        group=pl.ENTRY_POINT_GROUP)
    real_eps = importlib.metadata.entry_points

    def entry_points(**kw):
        if kw.get("group") == pl.ENTRY_POINT_GROUP:
            return importlib.metadata.EntryPoints([fake])
        return real_eps(**kw)

    monkeypatch.setattr(importlib.metadata, "entry_points", entry_points)
    src = _stage(tmp_path)
    out = tmp_path / "out"
    rc = main(["index", str(src), "--out", str(out)])
    err = capsys.readouterr().err
    assert rc != 0
    report = json.loads(err.strip().splitlines()[-1])
    assert report["status"] == "error"
    assert (report["plane"], report["axis"], report["value"]) == (
        "deontic", "operator", OOV_OPERATOR)
    assert not out.exists(), "a failed run must write nothing"
    assert sorted(p.name for p in src.iterdir()) == ["policy.txt", SIDECAR.name]
