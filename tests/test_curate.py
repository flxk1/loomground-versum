"""The curation loop — deterministic claim→concept suggester, then confirm.

Proves the concept layer can be built without hand-authoring: definitions seed concepts,
mentions link claims, cross-source support is measured, and confirm() writes a graph that
passes the invariants and supports the both-ways traversal.
"""
from pathlib import Path

from versum.store.index import index_folder
from versum.concept import curate
from versum.store import graph as g
import versum.profiles  # noqa: F401


def _corpus(root: Path):
    # generic markers: "is defined as", "means", "causes".
    # The concept seed now comes from the quoted definition scan (definitions.csv),
    # so the defined term is quoted; mentions in other claims link it cross-source.
    (root / "f1.md").write_text(
        "'Consent' is defined as agreement. Trust causes consent to be valid.\n",
        encoding="utf-8")
    (root / "f2.md").write_text(
        "Pressure causes consent to be doubtful in every case.\n", encoding="utf-8")


def test_suggest_seeds_and_links(tmp_path):
    _corpus(tmp_path)
    index_folder(tmp_path, "generic")
    rep = curate.suggest_folder(tmp_path)
    assert rep["n_suggested_concepts"] >= 1
    assert rep["n_suggested_edges"] >= 2
    # 'consent' was defined in f1 and mentioned in f2 -> cross-source
    assert rep["cross_source"] >= 1
    q = tmp_path / ".versum" / "curation"
    assert (q / "suggested_concepts.csv").exists()
    assert (q / "suggested_edges.csv").exists()


def test_confirm_builds_valid_graph(tmp_path):
    _corpus(tmp_path)
    index_folder(tmp_path, "generic")
    curate.suggest_folder(tmp_path)
    # keep only convergent concepts (grounded from >=2 sources)
    rep = curate.confirm_folder(tmp_path, min_sources=2)
    assert "consent" in rep["concept_ids"]

    v = tmp_path / ".versum"
    claims = g.load_claims(v / "claims.csv")
    concepts = g.load_concepts(v / "concepts.csv")
    edges = g.load_edges(v / "semantic_edges.csv")

    # invariants hold on the auto-built graph
    urns = {c["source_urn"] for c in claims}
    assert g.check_no_orphan_edges(claims, concepts, edges) == []
    assert g.check_concept_ids_own_identity(concepts, urns) == []

    # both-ways works: 'consent' is grounded from both files
    srcs = g.sources_for_model("consent", claims, edges)
    assert len(srcs) == 2


def test_recurrence_mining_finds_cross_source_concepts(tmp_path):
    # 'data portability' is never formally defined, but recurs in claims of two
    # sources — rung 1.5 must surface it. Dilution claims keep its claim-share
    # under the statistical function-word ceiling (MAX_CLAIM_SHARE).
    (tmp_path / "f1.md").write_text(
        "Data portability causes friction. Consent causes trust. "
        "Notice causes clarity. Storage causes cost.\n", encoding="utf-8")
    (tmp_path / "f2.md").write_text(
        "Data portability causes debate. Data portability causes effort. "
        "Pricing causes concern. Delay causes doubt. Volume causes strain.\n",
        encoding="utf-8")
    index_folder(tmp_path, "generic")
    rep = curate.suggest_folder(tmp_path)
    assert rep["n_recurrence"] >= 1
    assert rep["cross_source"] >= 1

    rows = (tmp_path / ".versum" / "curation" / "suggested_concepts.csv").read_text(
        encoding="utf-8")
    assert "data-portability" in rows
    # the marker verb rides in every claim — statistically common, never a concept
    assert "causes" not in [r.split(",")[0] for r in rows.splitlines()]

    # the mined concept promotes like any other and is convergent
    rep2 = curate.confirm_folder(tmp_path, min_sources=2)
    assert "data-portability" in rep2["concept_ids"]


def test_function_words_never_seed_or_frame_concepts(tmp_path):
    # 'der Vertrag' recurs cross-source; the article must not survive as a concept
    # or as a gram boundary — the concept is 'vertrag', not 'der-vertrag'. And an
    # English closed-class word ('for') stays out even at mid frequency.
    (tmp_path / "f1.md").write_text(
        "Der Vertrag causes Bindung. Consent causes trust. Notice causes clarity. "
        "Storage causes cost for archives.\n", encoding="utf-8")
    (tmp_path / "f2.md").write_text(
        "Der Vertrag causes Pflichten. Der Vertrag causes Rechte. "
        "Pricing causes concern for buyers. Delay causes doubt. Volume causes strain.\n",
        encoding="utf-8")
    index_folder(tmp_path, "generic")
    curate.suggest_folder(tmp_path)
    rows = (tmp_path / ".versum" / "curation" / "suggested_concepts.csv").read_text(
        encoding="utf-8")
    ids = [r.split(",")[0] for r in rows.splitlines()[1:]]
    assert "vertrag" in ids
    for bad in ("der", "for", "der-vertrag"):
        assert bad not in ids, ids


def test_marker_verbs_never_become_concepts(tmp_path):
    # every claim exists because a marker matched, so marker words recur by
    # construction. 'causes' rides in only 3 of 10 claims (under the statistical
    # ceiling) — the profile-marker exclusion must still keep it out.
    (tmp_path / "f1.md").write_text(
        "Frost causes damage. Heat causes stress. 'Consent' means agreement. "
        "'Notice' means information. 'Term' means duration.\n", encoding="utf-8")
    (tmp_path / "f2.md").write_text(
        "Drought causes famine. 'Deposit' means payment. 'Balance' means rest. "
        "'Fee' means charge. 'Rate' means price.\n", encoding="utf-8")
    index_folder(tmp_path, "generic")
    curate.suggest_folder(tmp_path)
    rows = (tmp_path / ".versum" / "curation" / "suggested_concepts.csv").read_text(
        encoding="utf-8")
    ids = [r.split(",")[0] for r in rows.splitlines()[1:]]
    assert "causes" not in ids, ids
    assert "means" not in ids, ids


def test_inflections_merge_into_one_concept(tmp_path):
    # 'Werk' / 'Werke' / 'Werkes' are one term; no single surface form reaches
    # MIN_CLAIMS alone, but the stem family does — and it must arrive as ONE
    # candidate ('werk') carrying the surface variants as labels.
    (tmp_path / "f1.md").write_text(
        "Das Werk causes Bindung. Die Werke causes Freude. Consent causes trust. "
        "Notice causes clarity. Storage causes cost.\n", encoding="utf-8")
    (tmp_path / "f2.md").write_text(
        "Des Werkes causes Pflichten. Pricing causes concern. Delay causes doubt. "
        "Volume causes strain. Interest causes debate.\n", encoding="utf-8")
    index_folder(tmp_path, "generic")
    curate.suggest_folder(tmp_path)
    import csv as _csv
    with open(tmp_path / ".versum" / "curation" / "suggested_concepts.csv",
              encoding="utf-8", newline="") as fh:
        rows = {r["concept_id"]: r for r in _csv.DictReader(fh)}
    assert "werk" in rows, rows.keys()
    assert int(rows["werk"]["n_sources"]) == 2
    assert int(rows["werk"]["n_claims"]) >= 3
    for split_id in ("werke", "werkes"):
        assert split_id not in rows, rows.keys()


def test_umlaut_plurals_merge_via_snowball(tmp_path):
    # German ablaut plurals (Fall/Fälle/Fällen, Vertrag/Verträge) only converge via
    # the Snowball german backend; the umlaut itself routes the word there.
    import pytest
    pytest.importorskip("snowballstemmer")
    from versum.concept.morph import stem_word
    assert stem_word("Fällen") == stem_word("Fälle") == stem_word("Fall") == "fall"
    assert stem_word("Verträge") == stem_word("Vertrag") == "vertrag"

    (tmp_path / "f1.md").write_text(
        "Der Fall causes Prüfung. Die Fälle causes Arbeit. Consent causes trust. "
        "Notice causes clarity. Storage causes cost.\n", encoding="utf-8")
    (tmp_path / "f2.md").write_text(
        "In diesen Fällen causes Aufwand. Pricing causes concern. Delay causes doubt. "
        "Volume causes strain. Interest causes debate.\n", encoding="utf-8")
    index_folder(tmp_path, "generic")
    curate.suggest_folder(tmp_path)
    import csv as _csv
    with open(tmp_path / ".versum" / "curation" / "suggested_concepts.csv",
              encoding="utf-8", newline="") as fh:
        rows = {r["concept_id"]: r for r in _csv.DictReader(fh)}
    assert "fall" in rows, rows.keys()
    assert int(rows["fall"]["n_sources"]) == 2
    assert "faell" not in rows and "faelle" not in rows, rows.keys()


def test_slugs_transliterate_umlauts(tmp_path):
    assert curate._slug("Unabhängige Musikverleger") == "unabhaengige-musikverleger"
    assert curate._slug("für") == "fuer"
    from versum.io.extract import _term_slug
    assert _term_slug("Übertragung") == "uebertragung"
    assert _term_slug("Café") == "cafe"


def test_confirm_threshold_filters(tmp_path):
    _corpus(tmp_path)
    index_folder(tmp_path, "generic")
    curate.suggest_folder(tmp_path)
    # a very high threshold keeps nothing
    rep = curate.confirm_folder(tmp_path, min_sources=99)
    assert rep["n_concepts"] == 0
