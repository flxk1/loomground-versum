"""Text hygiene — extracted text (and therefore claim text) carries no NUL / control chars.

A PDF text layer sometimes emits NUL (0x00) and other C0 control characters; written into a
CSV they break strict parsers and pollute claim text. The extractor strips them at ingestion
(keeping tab + newline), before segmentation, so span offsets stay consistent.
"""
from versum.io import extract as ex
from versum.store import index as idx, graph as g
import versum.profiles  # noqa: F401 — register built-ins


def test_clean_text_strips_nul_and_controls_keeps_tab_newline():
    dirty = "A\x00B\x07 shall\x0b ensure.\tkept\nkept"
    clean = ex.clean_text(dirty)
    assert "\x00" not in clean and "\x07" not in clean and "\x0b" not in clean
    assert "\t" in clean and "\n" in clean       # tab + newline preserved
    assert clean == "AB shall ensure.\tkept\nkept"


def test_indexed_claim_text_has_no_nul(tmp_path):
    (tmp_path / "doc.txt").write_text(
        "The controller shall\x00 ensure protection. 'Data' is defined\x00 as info.\n",
        encoding="utf-8")
    idx.index_folder(tmp_path, "law-eu")
    claims = g.load_claims(tmp_path / ".versum" / "claims.csv")
    assert claims, "expected claims from the text file"
    assert all("\x00" not in (c.get("text") or "") for c in claims), "NUL leaked into claim text"
