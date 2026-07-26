"""The guard at the door — deterministic write pipeline, no LLM.

Proves: identity resolution (CELEX/path-slug), dedup, idempotent capture (adding a file
admits only the new one), and that the whole graph persists in <folder>/.versum/.
"""
from pathlib import Path

from versum import write as w
from versum.profile import get_profile
import versum.profiles  # noqa: F401


def _seed(root: Path):
    (root / "one.md").write_text("Alpha is defined as the first. Beta causes gamma.\n",
                                 encoding="utf-8")
    (root / "two.txt").write_text("Delta is defined as the fourth letter.\n",
                                  encoding="utf-8")


def test_identity_celex():
    prof = get_profile("law-eu")
    ident = w.resolve_identity(Path("CELEX%3A32016R0679%3AEN%3ATXT.pdf"), prof)
    assert ident.urn == "urn:dls:celex:32016r0679"
    assert ident.method == "celex"


def test_identity_path_slug_fallback():
    prof = get_profile("generic")
    ident = w.resolve_identity(Path("my random notes.md"), prof)
    assert ident.urn.startswith("urn:kg:source:")
    assert ident.method == "path-slug"


def test_ladder_only_fires_on_ambiguous(tmp_path):
    prof = get_profile("generic")
    called = {"n": 0}

    def resolver(ctx):
        called["n"] += 1
        return {"urn": "urn:kg:source:from-ladder", "method": "local-llm"}

    # CELEX name is unambiguous -> ladder must NOT be called
    w.resolve_identity(Path("CELEX%3A32016R0679.pdf"), get_profile("law-eu"), resolver)
    assert called["n"] == 0
    # a bare name is ambiguous -> ladder IS consulted
    ident = w.resolve_identity(Path("scan0001.md"), prof, resolver)
    assert called["n"] == 1 and ident.method == "local-llm"


def test_capture_and_persist(tmp_path):
    _seed(tmp_path)
    rep = w.capture_folder(tmp_path, "generic")
    assert rep["n_admitted"] == 2 and rep["n_duplicates"] == 0
    v = tmp_path / ".versum"
    # everything persists on disk
    for name in ("source_registry.csv", "claims.csv", "sources.csv",
                 "fingerprints.json", "concepts.csv", "semantic_edges.csv"):
        assert (v / name).exists()
    assert (v / "stubs").is_dir()
    reg = w.load_registry(tmp_path)
    assert len(reg) == 2


def test_capture_is_idempotent_and_incremental(tmp_path):
    _seed(tmp_path)
    w.capture_folder(tmp_path, "generic")
    # re-run with no change -> nothing new admitted
    rep2 = w.capture_folder(tmp_path, "generic")
    assert rep2["n_admitted"] == 0 and rep2["n_duplicates"] == 2
    # drop in a new document -> ONLY it is admitted
    (tmp_path / "three.md").write_text("Epsilon is defined as the fifth.\n", encoding="utf-8")
    rep3 = w.capture_folder(tmp_path, "generic")
    assert rep3["n_admitted"] == 1 and rep3["n_duplicates"] == 2
    assert len(w.load_registry(tmp_path)) == 3


def test_dedup_by_content_hash(tmp_path):
    _seed(tmp_path)
    w.capture_folder(tmp_path, "generic")
    # same bytes, different name -> caught as duplicate_hash, not re-admitted
    (tmp_path / "one_copy.md").write_text(
        (tmp_path / "one.md").read_text(encoding="utf-8"), encoding="utf-8")
    rep = w.capture_folder(tmp_path, "generic")
    assert rep["n_admitted"] == 0
    assert any(d["reason"] == "duplicate_hash" for d in rep["duplicates"])
