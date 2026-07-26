"""The guard's identity resolution + dedup — deterministic, no LLM.

Covers ``resolve_identity`` across the resolver ladder (DOI / arXiv / CELEX / path-slug),
``content_hash`` stability, the three ``dedup`` reasons, ``write_stub`` + sidecar, and a
single-source ``capture_file``.

NOTE on the DOI case: a DOI needs a real '/' to match, and the filename is URL-unquoted
first, so a Zotero-style ``10.1000%2Fxyz123`` name resolves to a DOI. A name with plain
underscores (e.g. ``paper_10.1000_xyz123.pdf``) has no slash and no word boundary before
the ``10``, so it falls through to a path-slug — see ``test_doi_underscore_name_is_path_slug``.
"""
from pathlib import Path

import pytest

from versum import write as w
from versum.profile import get_profile
import versum.profiles  # noqa: F401 — register built-ins


def test_resolve_doi_filename():
    ident = w.resolve_identity(Path("10.1000%2Fxyz123"), get_profile("generic"))
    assert ident.urn == "urn:kg:doi:10.1000/xyz123"
    assert ident.method == "doi"
    assert ident.identifier == "10.1000/xyz123"
    assert ident.verification == "metadata"


def test_doi_underscore_name_is_path_slug():
    # documents real behaviour: no slash -> not a DOI, falls to path-slug
    ident = w.resolve_identity(Path("paper_10.1000_xyz123.pdf"), get_profile("generic"))
    assert ident.method == "path-slug"
    assert ident.urn.startswith("urn:kg:source:")


def test_resolve_arxiv_filename():
    ident = w.resolve_identity(Path("2101.00001.pdf"), get_profile("generic"))
    assert ident.urn == "urn:kg:arxiv:2101.00001"
    assert ident.method == "arxiv"
    assert ident.verification == "metadata"


def test_resolve_celex_law_eu():
    ident = w.resolve_identity(
        Path("CELEX%3A32016R0679%3AEN%3ATXT.pdf"), get_profile("law-eu"))
    assert ident.urn == "urn:dls:celex:32016r0679"
    assert ident.method == "celex"


def test_resolve_plain_name_path_slug():
    ident = w.resolve_identity(Path("my meeting notes.md"), get_profile("generic"))
    assert ident.urn == "urn:kg:source:my-meeting-notes"
    assert ident.method == "path-slug"
    assert ident.verification == "filename"


def test_content_hash_stable_and_differs(tmp_path):
    a = tmp_path / "a.bin"; a.write_bytes(b"identical bytes")
    b = tmp_path / "b.bin"; b.write_bytes(b"identical bytes")
    c = tmp_path / "c.bin"; c.write_bytes(b"different bytes")
    assert w.content_hash(a) == w.content_hash(b)
    assert w.content_hash(a) != w.content_hash(c)


def test_dedup_duplicate_hash():
    reg = [{"urn": "urn:kg:source:a", "sha1": "SHA", "title": "Alpha"}]
    hit = w.dedup(reg, "urn:kg:source:zzz", "SHA", "Totally Other Title")
    assert hit is not None
    reason, existing = hit
    assert reason == "duplicate_hash"
    assert existing["urn"] == "urn:kg:source:a"


def test_dedup_duplicate_urn():
    reg = [{"urn": "urn:kg:source:a", "sha1": "SHA1", "title": "Alpha"}]
    # same urn, different sha AND different title -> caught on urn
    hit = w.dedup(reg, "urn:kg:source:a", "SHA2", "Beta")
    assert hit is not None and hit[0] == "duplicate_urn"


def test_dedup_duplicate_title():
    reg = [{"urn": "urn:kg:source:a", "sha1": "SHA1", "title": "Alpha"}]
    # different urn, different sha, but same title (case-insensitive)
    hit = w.dedup(reg, "urn:kg:source:b", "SHA2", "alpha")
    assert hit is not None and hit[0] == "duplicate_title"


def test_dedup_none_when_novel():
    reg = [{"urn": "urn:kg:source:a", "sha1": "SHA1", "title": "Alpha"}]
    assert w.dedup(reg, "urn:kg:source:b", "SHA2", "Beta") is None


def test_write_stub_and_sidecar(tmp_path):
    ident = w.Identity(
        urn="urn:kg:source:demo", identifier="demo", method="path-slug",
        title="Demo Title", verification="filename")
    src = tmp_path / "demo.md"; src.write_text("hi", encoding="utf-8")
    stub = w.write_stub(tmp_path, ident, src)

    stubs = tmp_path / ".versum" / "stubs"
    assert (stubs / stub).exists()
    sidecar_path = stubs / (stub + ".metadata.json")
    assert sidecar_path.exists()

    import json
    sc = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sc["sidecar_canonical"] == ident.urn
    assert sc["identity_method"] == "path-slug"
    assert sc["source_file"] == "demo.md"


def test_capture_file_single_source(tmp_path):
    src_dir = tmp_path / "corpus"; src_dir.mkdir()
    f = src_dir / "notes.md"
    f.write_text("Alpha is defined as first. Beta causes gamma.\n", encoding="utf-8")

    res = w.capture_file(f, tmp_path, "generic", reindex=False)
    assert res["admitted"] is True
    # a real file on disk with no canonical id / title -> content-hash rung, not filename.
    assert res["method"] == "content-sha256"
    assert res["urn"].startswith("urn:kg:sha256:")
    assert "index" not in res  # reindex=False

    reg = w.load_registry(tmp_path)
    assert len(reg) == 1
    row = reg[0]
    for col in w.REGISTRY_COLUMNS:
        assert col in row
    assert row["verification"]  # present, non-empty
    assert row["urn"] == res["urn"]


def test_resolver_falls_back_to_path_slug_on_none():
    calls = []

    def resolver(ctx):
        calls.append(ctx["name"])
        return None  # ladder declines -> path-slug fallback

    ident = w.resolve_identity(Path("scan0001.md"), get_profile("generic"), resolver)
    assert ident.method == "path-slug"
    assert ident.urn == "urn:kg:source:scan0001"
    assert calls == ["scan0001.md"]  # ladder WAS consulted for the ambiguous case


def test_resolver_not_called_for_unambiguous_names():
    calls = []

    def resolver(ctx):
        calls.append(1)
        return {"urn": "urn:kg:source:from-ladder", "method": "ladder"}

    # unambiguous CELEX -> resolver never fires; ladder urn never used
    ci = w.resolve_identity(Path("CELEX_32016R0679.pdf"), get_profile("law-eu"), resolver)
    assert ci.method == "celex" and calls == []
    # unambiguous DOI -> resolver never fires either
    di = w.resolve_identity(Path("10.1000%2Fabc999"), get_profile("generic"), resolver)
    assert di.method == "doi" and calls == []
