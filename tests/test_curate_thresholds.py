"""More curation coverage — the deterministic claim→concept suggester + confirm gate.

Uses the generic profile (namespace ``kg``); no domain gold data.
"""
from pathlib import Path

from versum.store.index import index_folder
from versum.concept import curate
import versum.profiles  # noqa: F401 — register built-ins


def _corpus(root: Path):
    # 'consent' defined in f1, mentioned again in f2  -> 2 sources (convergent)
    # 'notice' defined + mentioned only in f3          -> 1 source
    (root / "f1.md").write_text(
        "'Consent' is defined as agreement. Trust causes consent to be valid.\n",
        encoding="utf-8")
    (root / "f2.md").write_text(
        "Pressure causes consent to be doubtful in every case.\n", encoding="utf-8")
    (root / "f3.md").write_text(
        "'Notice' means information. Notice is helpful.\n", encoding="utf-8")


def test_confirm_min_sources_2_keeps_convergent_only(tmp_path):
    _corpus(tmp_path)
    index_folder(tmp_path, "generic")
    curate.suggest_folder(tmp_path)
    rep = curate.confirm_folder(tmp_path, min_sources=2)
    assert rep["concept_ids"] == ["consent"]      # only the cross-source concept
    assert "notice" not in rep["concept_ids"]


def test_confirm_min_sources_99_keeps_none(tmp_path):
    _corpus(tmp_path)
    index_folder(tmp_path, "generic")
    curate.suggest_folder(tmp_path)
    rep = curate.confirm_folder(tmp_path, min_sources=99)
    assert rep["n_concepts"] == 0
    assert rep["concept_ids"] == []


def test_confirm_only_concepts_overrides_threshold(tmp_path):
    _corpus(tmp_path)
    index_folder(tmp_path, "generic")
    curate.suggest_folder(tmp_path)
    # 'notice' has only 1 source, but an explicit allowlist keeps exactly it
    rep = curate.confirm_folder(tmp_path, min_sources=2, only_concepts={"notice"})
    assert rep["concept_ids"] == ["notice"]


def test_defined_but_unmentioned_concept_not_suggested():
    # a definition seeds a candidate, but with no claim mentioning its label it drops
    claims = [{"item_id": "i1", "text": "Something completely unrelated.",
               "source_urn": "S1"}]
    defs = [{"term": "zebra", "term_slug": "zebra"}]
    concepts, edges = curate.suggest(claims, defs)
    assert [c["concept_id"] for c in concepts] == []
    assert edges == []


def test_mention_re_word_boundaries():
    r = curate._mention_re("act")
    assert r.search("the act was passed")          # standalone -> match
    assert not r.search("they react quickly")       # inside 'react' -> no match
    assert not r.search("a faction formed")         # inside 'faction' -> no match


def test_mention_re_plural_tolerance():
    r = curate._mention_re("data subject")
    assert r.search("a data subject has rights")     # exact
    assert r.search("the data subjects have rights")  # trailing plural tolerated


def test_existing_concepts_are_link_targets():
    # a curator-authored concept (not from any definition) still gets linked by mention
    claims = [{"item_id": "i1", "text": "The widget spins fast.", "source_urn": "S1"}]
    existing = [{"concept_id": "widget", "label": "widget"}]
    concepts, edges = curate.suggest(claims, definitions=[], existing_concepts=existing)
    assert [c["concept_id"] for c in concepts] == ["widget"]
    assert edges and edges[0]["src_id"] == "i1" and edges[0]["dst_id"] == "widget"
    assert edges[0]["edge_type"] == "grounds"
