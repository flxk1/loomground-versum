"""The entries.csv span invariant: ``raw[span_start:span_end] == text`` for EVERY entry.

Spans index the unmodified decoded source (CRLF kept), so the ``text`` column must be that
exact slice — not a cleaned form with CR or C0 control characters removed. Each source here
carries a CR or a C0 control (``\\x0b``) *inside* a sentence and inside an embedded clause
(the fake plane's ``nests`` sub-span), so both sentence and embedded entries are exercised.

G3: ``raw`` is computed in the test from the fixture bytes, never from the indexer's output,
and the expected embedded-clause texts are written out literally.
"""
from __future__ import annotations

import csv
import importlib
from pathlib import Path

import pytest

from versum.store.index import index_folder

FIXTURES = Path(__file__).parent / "fixtures" / "planes_fake"

# (a) a CR inside a sentence and inside an embedded clause, in a CRLF file
CR_BYTES = (b"Ann walks\rhome today.\r\n\r\n"
            b"Bob shouts that the dog\rbarks at night.\r\n")
# (b) a C0 control (vertical tab) inside a sentence and inside an embedded clause
C0_BYTES = (b"Carla reads\x0bthe letter.\n\n"
            b"Dana thinks that rain\x0bhelps plants.\n")

CASES = {
    "cr": (CR_BYTES, "\r", "the dog\rbarks at night"),
    "c0": (C0_BYTES, "\x0b", "rain\x0bhelps plants"),
}


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURES))
    import fake_plane
    return importlib.reload(fake_plane)


def _index(tmp_path: Path, fake, data: bytes) -> tuple[str, list[dict]]:
    (tmp_path / "doc.txt").write_bytes(data)
    index_folder(tmp_path, "generic", planes=[fake.plane])
    with open(tmp_path / ".versum" / "entries.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return data.decode("utf-8"), rows


@pytest.mark.parametrize("case", sorted(CASES))
def test_every_entry_text_is_the_exact_source_slice(tmp_path, fake, case):
    data, _ctrl, _clause = CASES[case]
    raw, rows = _index(tmp_path, fake, data)
    assert rows, "no entries were written"
    for r in rows:
        s, e = int(r["span_start"]), int(r["span_end"])
        assert raw[s:e] == r["text"], (r["entry_kind"], s, e, r["text"])


@pytest.mark.parametrize("case", sorted(CASES))
def test_control_character_survives_in_sentence_and_embedded_entries(tmp_path, fake, case):
    data, ctrl, clause = CASES[case]
    raw, rows = _index(tmp_path, fake, data)
    kinds = {r["entry_kind"] for r in rows}
    assert kinds == {"sentence", "embedded"}, kinds
    sentences_with_ctrl = [r for r in rows if r["entry_kind"] == "sentence"
                           and ctrl in r["text"]]
    assert len(sentences_with_ctrl) == 2  # the plain sentence and the embedding one
    embedded = [r for r in rows if r["entry_kind"] == "embedded"]
    assert [r["text"] for r in embedded] == [clause]
    s = raw.index(clause)
    assert (int(embedded[0]["span_start"]), int(embedded[0]["span_end"])) == \
        (s, s + len(clause))
