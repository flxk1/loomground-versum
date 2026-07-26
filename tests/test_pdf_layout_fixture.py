from pathlib import Path

from versum.io.extract import extract_text


FIXTURES = Path(__file__).parent / "fixtures" / "pdf"


def _text(name: str) -> str:
    return extract_text(str(FIXTURES / name))


def test_line_break_regression_preserves_all_fixture_words():
    broken_layout = _text("line-break-regression.pdf")
    control = _text("single-line-control.pdf")
    expected = {"one", "two", "huge", "three", "four"}
    assert expected <= set(broken_layout.lower().split())
    assert expected <= set(control.lower().split())
