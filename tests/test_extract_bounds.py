"""Bounds on PDF parsing: an untrusted document can be a decompression/page bomb.

extract_text enforces a byte cap (before the pdf library is even imported) and a
page cap (after open), raising ValueError so the ingestion boundary records the
file as a per-file error instead of loading it wholesale. These tests exercise
the byte-cap path, which needs no pdfplumber, plus the config surface.
"""
import os
import tempfile

import pytest

from versum.io import extract


def _tmp_pdf(nbytes: int) -> str:
    fh = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    fh.write(b"%PDF-1.4\n" + b"0" * max(0, nbytes - 9))
    fh.close()
    return fh.name


def test_over_byte_cap_raises_before_parsing():
    path = _tmp_pdf(2000)
    try:
        with pytest.raises(ValueError, match="byte cap|VERSUM_MAX_PDF_BYTES"):
            extract.extract_text(path, max_bytes=1000)
    finally:
        os.unlink(path)


def test_under_byte_cap_does_not_raise_on_the_bound_itself():
    # A small file under the cap must pass the byte guard. It may still fail later
    # (missing pdfplumber, or its native deps panicking as a BaseException in some
    # envs) — that's unrelated; only assert our byte-cap ValueError does NOT fire.
    path = _tmp_pdf(100)
    try:
        extract.extract_text(path, max_bytes=1000)
    except ValueError as e:
        assert "byte cap" not in str(e), "byte guard must not fire under the cap"
    except BaseException:
        pass  # pdfplumber import / native panic is unrelated to the bound
    finally:
        os.unlink(path)


def test_defaults_are_present_and_env_overridable_shape():
    assert isinstance(extract.MAX_PDF_BYTES, int) and extract.MAX_PDF_BYTES > 0
    assert isinstance(extract.MAX_PDF_PAGES, int) and extract.MAX_PDF_PAGES > 0
