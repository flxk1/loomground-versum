"""Table-region skipping in the PDF extractor: ruled-table cells are dropped, prose is
kept, and the filter is opt-out. Table detection is geometric (ruling lines) — the same
mechanism pdfplumber's find_tables uses — never content-based.

reportlab is required for these tests; they skip if it is unavailable.
"""
import pytest

pytest.importorskip("reportlab")
pytest.importorskip("pdfplumber")

from versum.io import extract as ex        # noqa: E402
from tests import _pdf_battery as bat       # noqa: E402


def test_table_cells_are_skipped_prose_is_kept(tmp_path):
    path, prose, cell_words = bat.build_table(tmp_path)
    text = ex.extract_text(path)
    for line in prose:
        assert line in text, text
    for w in cell_words:
        assert w not in text, (w, text)


def test_skip_tables_is_opt_out(tmp_path):
    path, prose, cell_words = bat.build_table(tmp_path)
    text = ex.extract_text(path, skip_tables=False)
    for line in prose:
        assert line in text, text
    # without the filter the cell salad is back — proving the filter did the work
    assert any(w in text for w in cell_words), text


def test_pages_without_tables_are_untouched(tmp_path):
    path, expected = bat.build_normal(tmp_path)
    got = [l for l in ex.extract_text(path).splitlines() if l.strip()]
    assert got == expected, got
