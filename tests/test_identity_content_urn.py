"""ADR-URN-2 — the identity spine is content-addressed, not filename-derived.

The hardened KB-1.3 gate, run from the engine side. The old filename fallback forked on
rename and collided on same-name; the content-sha256 rung closes both when bytes exist. Three
directions, plus the no-content degradation:

  1. content-invariance   — same bytes, DIFFERENT filename  -> SAME urn.
  2. collision-freedom    — DIFFERENT bytes, same filename   -> DIFFERENT urn.
  3. canonical precedence — a scheme id wins over both, regardless of filename.
  4. no-content last resort — a path with no local bytes falls to the filename slug (the
     only signal left for a citation-only source).

Deterministic; no network; no LLM.
"""
from pathlib import Path

from versum.identity.core import deterministic_identity
from versum.profile import get_profile
import versum.profiles  # noqa: F401 — register built-ins

PROF = get_profile("generic")  # DOI + arXiv schemes; no CELEX (keeps rung 0 quiet for plain files)


def _urn(path):
    return deterministic_identity(path, PROF)[0]


def _method(path):
    return deterministic_identity(path, PROF)[2]


# ── direction 1 — content-invariance: rename must NOT change the urn ───────────
def test_same_bytes_different_name_same_urn(tmp_path):
    body = b"Alpha is defined as the first letter. Beta causes gamma.\n"
    a = tmp_path / "original-name.txt"; a.write_bytes(body)
    b = tmp_path / "totally different name.txt"; b.write_bytes(body)

    ua, ub = _urn(a), _urn(b)
    assert _method(a) == "content-sha256", _method(a)
    assert ua == ub, f"rename forked identity: {ua!r} != {ub!r}"
    assert ua.startswith("urn:kg:sha256:")


def test_move_between_dirs_same_urn(tmp_path):
    body = b"Delta is defined as the fourth letter.\n"
    d1 = tmp_path / "domainA" / "2021"; d1.mkdir(parents=True)
    d2 = tmp_path / "domainB" / "1999"; d2.mkdir(parents=True)
    f1 = d1 / "same.txt"; f1.write_bytes(body)
    f2 = d2 / "same.txt"; f2.write_bytes(body)
    # same bytes, different shelf path AND same leaf name -> one identity
    assert _urn(f1) == _urn(f2)


# ── direction 2 — collision-freedom: same name, different bytes must differ ─────
def test_different_bytes_same_name_different_urn(tmp_path):
    d1 = tmp_path / "one"; d1.mkdir()
    d2 = tmp_path / "two"; d2.mkdir()
    a = d1 / "report.txt"; a.write_bytes(b"first document, unique content A\n")
    b = d2 / "report.txt"; b.write_bytes(b"second document, unique content B\n")

    ua, ub = _urn(a), _urn(b)
    assert ua != ub, f"same-name collision: two documents share {ua!r}"
    assert _method(a) == "content-sha256" and _method(b) == "content-sha256"


# ── direction 3 — canonical precedence: a scheme id beats content + filename ────
def test_canonical_id_beats_content(tmp_path):
    # a DOI in the filename -> rung 0 fires. Two REAL files with the same DOI but different
    # bytes and different names still yield ONE canonical urn: the scheme id outranks both the
    # content hash (which would differ) and the filename (which differs). A space bounds the
    # DOI cleanly, keeping the extension out of the id.
    a = tmp_path / "10.1000%2Fxyz999 version A.pdf"; a.write_bytes(b"body one\n")
    b = tmp_path / "10.1000%2Fxyz999 version B.pdf"; b.write_bytes(b"body two, different\n")
    ua, ma = deterministic_identity(a, PROF)[0], deterministic_identity(a, PROF)[2]
    ub = deterministic_identity(b, PROF)[0]
    assert ma == "doi"
    assert ua == ub == "urn:kg:doi:10.1000/xyz999"


# ── direction 4 — no-content last resort: filename slug only when nothing to hash ─
def test_no_local_bytes_falls_to_filename(tmp_path):
    # a path that does not exist (a citation-only record) -> nothing to hash -> filename slug.
    ghost = tmp_path / "citation only never fetched.md"  # not written
    urn, ident, method, title, verif = deterministic_identity(ghost, PROF)
    assert method == "path-slug" and verif == "filename"
    assert urn == "urn:kg:source:citation-only-never-fetched"


# ── the fork/collision the OLD scheme exhibited is gone (regression pin) ────────
def test_old_filename_fork_is_closed(tmp_path):
    body = b"identical bytes under two names\n"
    x = tmp_path / "aaa.txt"; x.write_bytes(body)
    y = tmp_path / "zzz.txt"; y.write_bytes(body)
    # OLD behaviour: urn:kg:source:aaa != urn:kg:source:zzz (a fork). NOW: equal.
    assert _urn(x) == _urn(y)


def test_celex_summary_is_a_distinct_document(tmp_path):
    """The _SUM qualifier is identity: a judgment and its official summary must not
    collapse into one URN; language codes remain presentation and still collapse."""
    law = get_profile("law-eu")
    full = deterministic_identity(tmp_path / "CELEX_61980CJ0055_DE_TXT.pdf", law)
    summary = deterministic_identity(tmp_path / "CELEX_61980CJ0055_SUM_DE_TXT.pdf", law)
    english = deterministic_identity(tmp_path / "CELEX_61980CJ0055_EN_TXT.pdf", law)
    assert full[0] == "urn:dls:celex:61980cj0055"
    assert summary[0] == "urn:dls:celex:61980cj0055_sum"
    assert english[0] == full[0]
