"""Phase 1 consume — proven against a REAL staged KG registry + inbox sidecars.

These run against real data staged on disk, not stubs:
  * a 19-column registry sample (799 data rows) at ``VERSUM_REGISTRY_CSV``, and
  * inbox capture sidecars (``*.metadata.json`` with ``canonical_urn``) at
    ``VERSUM_INBOX_DIR``.

They assert ADR-URN option B: a file already in the registry (or settled by a sidecar)
REUSES the KG's canonical_urn rather than minting a parallel one; a file absent from the
registry is flagged (the PDF-without-registry gap); and loop-8 namespace parameterisation
yields two distinct URNs for the same file under two libraries. Skipped unless both
environment variables are set, since the registry and sidecars are the user's own data.
"""
import csv
import os
from pathlib import Path

import pytest

from versum.io import consume
from versum.io.consume import read_registry, read_sidecars, missing_from_registry
from versum.store.index import index_folder
from versum.libraries import LibrariesRegistry
import versum.profiles  # noqa: F401 — register built-in profiles


def _env_path(var, kind):
    value = os.environ.get(var)
    if not value or not Path(value).exists():
        pytest.skip(f"set {var} to a real staged {kind} to run this test")
    return Path(value)


@pytest.fixture(scope="module")
def registry_path():
    return _env_path("VERSUM_REGISTRY_CSV", "registry CSV")


@pytest.fixture(scope="module")
def inbox_dir():
    return _env_path("VERSUM_INBOX_DIR", "inbox directory")


@pytest.fixture(scope="module")
def registry(registry_path):
    return read_registry(registry_path)


# ── (a) reading the registry yields 799 rows, each with a canonical_urn ──
def test_registry_has_799_rows_each_with_canonical_urn(registry):
    assert len(registry) == 799
    assert all((r.get("canonical_urn") or "").strip() for r in registry.rows)
    # the 19 authoritative columns are present, unshadowed
    assert set(consume.REGISTRY_COLUMNS).issubset(set(registry.rows[0].keys()))


# ── (b) a file whose relpath == a row's original_path reuses that canonical_urn ──
def test_reuse_urn_by_original_path(registry):
    row = registry.rows[0]
    relpath = row["original_path"]
    expected = row["canonical_urn"]
    assert relpath and expected
    # matched by relpath (primary) …
    assert registry.reuse_urn(relpath=relpath) == expected
    # … and by bare filename (fallback)
    assert registry.reuse_urn(filename=Path(relpath).name) == expected
    # it is the KG's own urn, not a freshly-minted urn:kg:source:… slug
    assert not expected.startswith("urn:kg:source:")


def test_reuse_urn_reused_through_index_pipeline(registry, tmp_path):
    """A text file at a registry relpath is indexed under the REUSED canonical_urn.

    Reuses a REAL canonical_urn from the staged registry, bound to a text relpath so the
    generic extractor can read it (the real rows are PDFs whose bytes are out-of-band).
    """
    real_urn = registry.rows[0]["canonical_urn"]
    reg = consume.Registry([{"original_path": "sub/note.md", "filename": "note.md",
                             "canonical_urn": real_urn, "version_urn": real_urn + ":v1",
                             "primary_topic": "T", "topics": "T; U",
                             "jurisdiction": "EU", "detected_year": "2021"}])
    fp = tmp_path / "sub" / "note.md"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("A widget is defined as a thing. A widget causes value.\n",
                  encoding="utf-8")
    m = index_folder(tmp_path, "generic", consume=reg, library="dls-knowledge")
    assert m["n_kg_reused"] == 1
    srcs = list(csv.DictReader(open(tmp_path / ".versum" / "sources.csv")))
    assert len(srcs) == 1
    s = srcs[0]
    assert s["source_urn"] == real_urn                  # reused, not minted
    assert s["provenance"] == "kg-registry"
    assert s["canonical_urn"] == real_urn               # provenance linkage carried
    assert s["library"] == "dls-knowledge"


# ── (c) same synthetic file, two libraries, two namespaces -> two DIFFERENT urns ──
def test_two_libraries_two_namespaces_two_urns(tmp_path):
    libs = LibrariesRegistry({
        "lib-a": {"root_path": str(tmp_path / "a"), "urn_namespace": "nsalpha"},
        "lib-b": {"root_path": str(tmp_path / "b"), "urn_namespace": "nsbeta"},
    })
    urns = {}
    for lib_id in ("lib-a", "lib-b"):
        root = libs.root_for(lib_id)
        root.mkdir(parents=True, exist_ok=True)
        # SAME relpath / same content under each library
        (root / "note.md").write_text(
            "A widget is defined as a thing. A widget causes value.\n", encoding="utf-8")
        m = index_folder(root, "generic",
                         namespace=libs.namespace_for(lib_id), library=lib_id)
        srcs = list(csv.DictReader(open(root / ".versum" / "sources.csv")))
        assert m["namespace"] == libs.namespace_for(lib_id)
        urns[lib_id] = srcs[0]["source_urn"]
    assert urns["lib-a"] != urns["lib-b"], urns
    assert urns["lib-a"].startswith("urn:nsalpha:")
    assert urns["lib-b"].startswith("urn:nsbeta:")


# ── (d) PDF-without-registry: a file absent from the registry is flagged ──
def test_missing_from_registry_flags_absent_file(registry):
    present = registry.rows[0]["original_path"]
    absent = "knowledge_library/__does_not_exist__/no-such-file-xyz.pdf"
    flagged = missing_from_registry([present, absent], registry)
    assert absent in flagged
    assert present not in flagged
    # de-dupes and preserves order
    assert missing_from_registry([absent, absent], registry) == [absent]


# ── (e) a sidecar's canonical_urn is read and reused ──
def test_sidecar_canonical_urn_read_and_reused(inbox_dir):
    sidecars = read_sidecars(inbox_dir)
    assert sidecars, "no inbox sidecars with a canonical_urn found"
    # every entry carries a non-empty canonical_urn keyed by stub name
    assert all(v["canonical_urn"] for v in sidecars.values())
    # pick any stub and confirm sidecar_urn_for reuses its canonical_urn
    stub, entry = next(iter(sidecars.items()))
    assert consume.sidecar_urn_for(stub, sidecars) == entry["canonical_urn"]
    assert consume.sidecar_urn_for("no-such-stub.md", sidecars) is None


def test_ambiguous_filename_refuses_to_guess():
    """A filename shared by rows with DIFFERENT canonical_urns must not be guessed.

    relpath (unique) still resolves each row; a filename-only lookup returns None so the
    caller falls back to deterministic minting rather than mis-keying a document.
    """
    rows = [
        {"original_path": "a/dup.pdf", "filename": "dup.pdf", "canonical_urn": "urn:x:source:aaa"},
        {"original_path": "b/dup.pdf", "filename": "dup.pdf", "canonical_urn": "urn:x:source:bbb"},
        {"original_path": "c/uniq.pdf", "filename": "uniq.pdf", "canonical_urn": "urn:x:source:ccc"},
    ]
    reg = consume.Registry(rows)
    # relpath resolves each colliding file to its OWN canonical_urn
    assert reg.reuse_urn(relpath="a/dup.pdf") == "urn:x:source:aaa"
    assert reg.reuse_urn(relpath="b/dup.pdf") == "urn:x:source:bbb"
    # filename-only on the collision refuses to guess
    assert reg.reuse_urn(filename="dup.pdf") is None
    # a unique filename still resolves by filename
    assert reg.reuse_urn(filename="uniq.pdf") == "urn:x:source:ccc"
