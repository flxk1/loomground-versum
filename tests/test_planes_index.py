"""Sentence entries, 5D positions, per-entry assignments/bindings and fail-closed
indexing, driven by the FAKE plane under ``tests/fixtures/planes_fake``."""
from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path

import pytest

from versum import planes as pl
from versum import position5d as p5
from versum.io.consume import Registry
from versum.nd import load_assignments, load_bindings
from versum.store.index import index_folder

FIXTURES = Path(__file__).parent / "fixtures" / "planes_fake"
FIVE = ("structural", "causal", "intentional", "temporal", "relational")


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURES))
    import fake_plane
    return importlib.reload(fake_plane)


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _entries(folder):
    return _rows(folder / ".versum" / "entries.csv")


def _store_bytes(v: Path) -> dict:
    return {p.relative_to(v).as_posix(): p.read_bytes()
            for p in sorted(v.rglob("*")) if p.is_file()}


def _with_produce(fake, produce, **overrides):
    d = fake.plane()
    d["produce"] = produce
    d.update(overrides)
    return d


TEXT = ("Ann walks home. Bob shouts at the dog! Carla thinks that rain helps plants.\n\n"
        "Dora sleeps\n")
SENTENCES = ["Ann walks home.", "Bob shouts at the dog!",
             "Carla thinks that rain helps plants.", "Dora sleeps"]


# ── A4: every sentence becomes an entry, independent of profile markers ──
@pytest.mark.parametrize("with_plane", [False, True])
def test_every_sentence_is_an_entry_with_exact_span_and_5d_position(fake, tmp_path,
                                                                   with_plane):
    (tmp_path / "a.txt").write_text(TEXT, encoding="utf-8")
    m = index_folder(tmp_path, "generic", planes=[fake.plane] if with_plane else None)
    assert m["n_claims"] == 0                          # no profile marker fired
    raw = (tmp_path / "a.txt").read_bytes().decode("utf-8")
    entries = _entries(tmp_path)
    sentence_entries = [e for e in entries if e["entry_kind"] == "sentence"]
    assert [e["text"] for e in sentence_entries] == SENTENCES
    for e in entries:
        s, t = int(e["span_start"]), int(e["span_end"])
        assert raw[s:t] == e["text"]                   # span slices the unmodified source
        position = {d: float(e[d]) for d in FIVE}
        assert set(position) == set(p5.DIMENSIONS) == set(FIVE)
        assert e["dominant_dimension"] in FIVE         # exactly one dominant dimension
        assert ";" not in e["dominant_dimension"]
    for sentence in SENTENCES:
        assert sum(e["text"] == sentence for e in sentence_entries) == 1


def test_span_indexes_unmodified_crlf_source(tmp_path):
    raw = "First line here.\r\n\r\nSecond one, too.\r\nStill second? Yes.\r\n"
    (tmp_path / "w.txt").write_bytes(raw.encode("utf-8"))
    index_folder(tmp_path, "generic")
    got = [(int(e["span_start"]), int(e["span_end"]), e["text"]) for e in _entries(tmp_path)]
    assert [t for _, _, t in got] == ["First line here.", "Second one, too.",
                                      "Still second?", "Yes."]
    assert all(raw[s:e] == t for s, e, t in got)


def test_no_plane_default_is_zero_position_relational(tmp_path):
    (tmp_path / "a.txt").write_text("Ann walks home.\n", encoding="utf-8")
    index_folder(tmp_path, "generic")
    (e,) = _entries(tmp_path)
    assert {d: float(e[d]) for d in FIVE} == {d: 0.0 for d in FIVE}
    assert e["dominant_dimension"] == "relational" == p5.NO_PLANE_DOMINANT
    assert e["position_basis"] == "default"
    assert e["item_id"] == pl.entry_id(e["source_urn"], 0, len("Ann walks home."))


def test_position_from_bindings_and_documented_tie_order(fake, tmp_path):
    (tmp_path / "a.txt").write_text("Bob shouts at the dog!\n", encoding="utf-8")
    index_folder(tmp_path, "generic", planes=[fake.plane])
    (e,) = _entries(tmp_path)
    # relation shouts -> intentional, bound field tone -> causal: a tie
    assert {d: float(e[d]) for d in FIVE} == {
        "structural": 0.0, "causal": 0.5, "intentional": 0.5, "temporal": 0.0,
        "relational": 0.0}
    assert e["dominant_dimension"] == "causal"         # causal precedes intentional
    assert e["position_basis"] == "planes"
    assert p5.TIE_ORDER == FIVE


def test_dominant_is_argmax_then_tie_order():
    assert p5.dominant({"temporal": 2, "structural": 1}) == "temporal"
    assert p5.dominant({"relational": 1, "structural": 1}) == "structural"
    assert p5.dominant({}) == "relational"
    with pytest.raises(ValueError):
        p5.position({"contextual": 1})


# ── embedded sub-span claims ──────────────────────────────────────
def test_embedded_claim_is_its_own_entry_linked_to_parent(fake, tmp_path):
    text = "Carla thinks that rain helps plants."
    (tmp_path / "a.txt").write_text(text + "\n", encoding="utf-8")
    index_folder(tmp_path, "generic", planes=[fake.plane])
    entries = {e["entry_kind"]: e for e in _entries(tmp_path)}
    parent, child = entries["sentence"], entries["embedded"]
    assert child["text"] == "rain helps plants"
    assert text[int(child["span_start"]):int(child["span_end"])] == child["text"]
    assert child["parent_id"] == parent["item_id"]
    links = _rows(tmp_path / ".versum" / "entry_links.csv")
    (link,) = [lk for lk in links if lk["dst_id"] == child["item_id"]]
    assert link["src_id"] == parent["item_id"]
    assert link["dimension"] in FIVE and link["dimension"] == pl.EMBED_LINK_DIMENSION
    assert all(lk["dimension"] in FIVE for lk in links)


def test_plane_link_is_typed_by_one_dimension(fake, tmp_path):
    (tmp_path / "a.txt").write_text("Gus shouts that Hal left.\n", encoding="utf-8")
    index_folder(tmp_path, "generic", planes=[fake.plane])
    entries = {e["entry_kind"]: e for e in _entries(tmp_path)}
    links = _rows(tmp_path / ".versum" / "entry_links.csv")
    typed = [lk for lk in links if lk["plane"] == "fakeplane"]
    assert typed == [{"link_id": typed[0]["link_id"], "src_id": entries["sentence"]["item_id"],
                      "dst_id": entries["embedded"]["item_id"], "dimension": "temporal",
                      "relation": "precedes", "plane": "fakeplane", "method": "fake-rule"}]


def test_nested_embedded_entry_gets_smallest_enclosing_parent(fake):
    sentence = "X says Y thinks Z rains."

    def produce(s, context=None):
        return [{"relation": "nests", "span": [7, 23], "coordinates": {}, "method": "m"},
                {"relation": "nests", "span": [16, 23], "coordinates": {}, "method": "m"}]

    built = pl.build_source_entries(sentence, "urn:t:1",
                                    pl.load_planes([_with_produce(fake, produce)]))
    by_text = {e["text"]: e for e in built.entries}
    assert by_text["Z rains"]["parent_id"] == by_text["Y thinks Z rains"]["item_id"]
    assert by_text["Y thinks Z rains"]["parent_id"] == by_text[sentence]["item_id"]


# ── A3: per-entry assignments and bindings ────────────────────────
def test_assignments_are_per_entry_version_locked_and_bindings_written(fake, tmp_path):
    (tmp_path / "a.txt").write_text(TEXT, encoding="utf-8")
    m = index_folder(tmp_path, "generic", planes=[fake.plane])
    v = tmp_path / ".versum"
    entry_ids = {e["item_id"] for e in _entries(tmp_path)}
    rows = [r for r in load_assignments(v / "nd" / "assignments.csv")
            if r["system_id"] == "fakeplane-system"]
    assert rows
    for r in rows:
        assert r["subject_id"] in entry_ids
        assert r["system_version"] == "0.0.1-test" == fake.plane()["language_version"]
        assert r["source_id"] and r["method"] == "fake-rule"
    bindings = load_bindings(v / "nd" / "bindings.csv")
    assert bindings and m["n_nd_bindings"] == len(bindings)
    assignment_ids = {r["assignment_id"] for r in rows}
    for b in bindings:
        assert b["claim_id"] in entry_ids
        assert b["form_slot"] == "clause.voice" and b["axis_id"] == "tone"
        assert b["assignment_id"] in assignment_ids
    claims = [json.loads(x) for x in (v / "entry_claims.jsonl").read_text().splitlines()]
    assert {c["item_id"] for c in claims} <= entry_ids


def test_core_source_coordinates_apply_to_every_entry(fake, tmp_path):
    (tmp_path / "a.txt").write_text(TEXT, encoding="utf-8")
    reg = Registry([{"original_path": "a.txt", "filename": "a.txt",
                     "canonical_urn": "urn:x:source:a", "jurisdiction": "EU",
                     "detected_year": "2020"}])
    index_folder(tmp_path, "generic", consume=reg, planes=[fake.plane])
    assignments = load_assignments(tmp_path / ".versum" / "nd" / "assignments.csv")
    for e in _entries(tmp_path):
        axes = {(a["axis_id"], json.dumps(a["value"])) for a in
                pl.entry_coordinates(e, assignments)}
        assert ("jurisdiction", '"EU"') in axes and ("time", '"2020"') in axes


def test_source_context_reaches_the_producer(fake):
    built = pl.build_source_entries("Ann shouts.", "urn:t:1", pl.load_planes([fake.plane]),
                                    context={"source": {"mood": "grey"}})
    assert {(a.axis_id, a.value) for a in built.assignments} == {
        ("tone", "loud"), ("mood", "grey")}


def test_index_is_deterministic(fake, tmp_path):
    (tmp_path / "a.txt").write_text(TEXT, encoding="utf-8")
    index_folder(tmp_path, "generic", planes=[fake.plane])
    first = _store_bytes(tmp_path / ".versum")
    index_folder(tmp_path, "generic", planes=[fake.plane])
    second = _store_bytes(tmp_path / ".versum")
    first.pop("index.json"); second.pop("index.json")
    assert first == second


# ── rule 4: published examples round-trip field for field ─────────
def test_plane_examples_round_trip_through_the_index(fake, tmp_path):
    plane = pl.load_planes([fake.plane])[0]
    for i, ex in enumerate(plane.examples()):
        (tmp_path / f"ex{i}.txt").write_text(ex["sentence"] + "\n", encoding="utf-8")
    index_folder(tmp_path, "generic", planes=[fake.plane])
    v = tmp_path / ".versum"
    sources = {r["path"]: r["source_urn"] for r in _rows(v / "sources.csv")}
    claims = [json.loads(x) for x in (v / "entry_claims.jsonl").read_text().splitlines()]
    for i, ex in enumerate(plane.examples()):
        got = [c["claim"] for c in claims if c["source_urn"] == sources[f"ex{i}.txt"]]
        assert got == ex["expected"]


# ── rule 6: fail closed ───────────────────────────────────────────
def _bad(fake, claim_patch):
    def produce(sentence, context=None):
        out = fake.produce(sentence, context)
        for c in out:
            claim_patch(c)
        return out
    return _with_produce(fake, produce)


BAD_OUTPUTS = [
    ("oov-value", lambda c: c["coordinates"].update(tone="shrill"), "tone", "shrill"),
    ("unknown-axis", lambda c: c["coordinates"].update(colour="red"), "colour", "red"),
    ("invalid-form-slot", lambda c: c.update(slots={"clause.nope": "tone"}), "tone", "loud"),
    ("axis-not-allowed-for-slot", lambda c: c.update(
        coordinates={"tone": "loud", "mood": "x"}, slots={"clause.voice": "mood"}),
     "mood", "x"),
    ("slot-without-value", lambda c: c.update(slots={"clause.voice": "mood"}), "mood", None),
    ("link-not-five", lambda c: c.update(links=[{"type": "contextual", "relation": "r",
                                                 "to_span": [0, 3]}]), "type", "contextual"),
    ("bad-span", lambda c: c.update(span=[0, 999]), None, None),
    ("no-method", lambda c: c.update(method=""), None, ""),
]


@pytest.mark.parametrize("name, patch, axis, value", BAD_OUTPUTS, ids=[b[0] for b in BAD_OUTPUTS])
def test_invalid_plane_output_aborts_index_and_writes_nothing(fake, tmp_path, name, patch,
                                                              axis, value):
    (tmp_path / "ok.txt").write_text("Bob naps.\n", encoding="utf-8")
    (tmp_path / "z.txt").write_text("Ann shouts.\n", encoding="utf-8")
    with pytest.raises(pl.PlaneIndexError) as info:
        index_folder(tmp_path, "generic", planes=[_bad(fake, patch)])
    err = info.value
    assert err.plane == "fakeplane" and "fakeplane" in str(err)
    assert err.axis == axis and err.value == value
    if value:
        assert repr(value) in str(err) and repr(axis) in str(err)
    assert not (tmp_path / ".versum").exists()        # nothing of the run was written


def test_non_five_binding_aborts_index_and_writes_nothing(fake, tmp_path):
    (tmp_path / "z.txt").write_text("Ann shouts.\n", encoding="utf-8")
    d = fake.plane()
    d["binding"]["shouts"] = "contextual"
    with pytest.raises(pl.PlaneDescriptorError, match="five dimensions"):
        index_folder(tmp_path, "generic", planes=[d])
    assert not (tmp_path / ".versum").exists()


def test_failed_reindex_leaves_previous_index_untouched(fake, tmp_path):
    (tmp_path / "z.txt").write_text("Ann shouts.\n", encoding="utf-8")
    index_folder(tmp_path, "generic", planes=[fake.plane])
    before = _store_bytes(tmp_path / ".versum")
    with pytest.raises(pl.PlaneIndexError):
        index_folder(tmp_path, "generic", planes=[
            _bad(fake, lambda c: c["coordinates"].update(tone="shrill"))])
    assert _store_bytes(tmp_path / ".versum") == before


def test_cli_index_exits_non_zero_naming_plane_axis_value(fake, monkeypatch, tmp_path, capsys):
    import importlib.metadata as md
    bad = _bad(fake, lambda c: c["coordinates"].update(tone="shrill"))
    monkeypatch.setattr(fake, "plane", lambda: bad)
    ep = md.EntryPoint(name="fakeplane", value="fake_plane:plane", group=pl.ENTRY_POINT_GROUP)
    real = md.entry_points
    monkeypatch.setattr(md, "entry_points", lambda **kw: md.EntryPoints([ep])
                        if kw.get("group") == pl.ENTRY_POINT_GROUP else real(**kw))
    from versum.__main__ import main
    (tmp_path / "z.txt").write_text("Ann shouts.\n", encoding="utf-8")
    assert main(["index", str(tmp_path)]) == 3
    err = json.loads(capsys.readouterr().err)
    assert (err["plane"], err["axis"], err["value"]) == ("fakeplane", "tone", "shrill")
    assert not (tmp_path / ".versum").exists()


def test_producer_exception_fails_closed(fake):
    def produce(sentence, context=None):
        raise RuntimeError("broken")
    with pytest.raises(pl.PlaneIndexError, match="producer raised RuntimeError"):
        pl.build_source_entries("Ann naps.", "urn:t:1",
                                pl.load_planes([_with_produce(fake, produce)]))


def test_unserialisable_claim_fails_closed(fake, tmp_path):
    (tmp_path / "z.txt").write_text("Ann shouts.\n", encoding="utf-8")
    with pytest.raises(pl.PlaneIndexError, match="JSON"):
        index_folder(tmp_path, "generic", planes=[
            _bad(fake, lambda c: c.update(extra={1, 2}))])
    assert not (tmp_path / ".versum").exists()
