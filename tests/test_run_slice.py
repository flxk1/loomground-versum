"""Phase 2 — derived pdf_status (loop 3) + the slice runner/ledger (loops 3/4).

Proven against .txt fixtures on disk and a small consume registry:

  (c) ``pdf_status`` returns 'processable' for a file that exists at root+relpath and
      'citation-only' for an absent relpath;
  (d) ``run_slice`` over a tiny mixed set (one registry-backed file → reused, one file
      absent from the registry → minted, one registry row with no bytes → citation-only,
      plus an off-domain registry row that must be excluded) returns a ledger with the right
      pdf_status per row and a summary whose counts and reuse_rate/mint_rate are correct.
"""
from versum.io import consume
from versum.libraries import LibrariesRegistry
from versum.run import pdf_status, run_slice
import versum.profiles  # noqa: F401 — register built-in profiles


# ── (c) pdf_status is DERIVED from the filesystem ────────────────────
def test_pdf_status_present_vs_absent(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "here.txt").write_text("x", encoding="utf-8")
    libs = LibrariesRegistry(
        {"lib": {"root_path": str(tmp_path), "urn_namespace": "ns-lib"}})
    assert pdf_status("sub/here.txt", libs, "lib") == "processable"
    assert pdf_status("sub/missing.pdf", libs, "lib") == "citation-only"
    # a directory is not a processable source file
    assert pdf_status("sub", libs, "lib") == "citation-only"


# ── (d) run_slice over a tiny mixed set ──────────────────────────────
def _marker_text(name):
    return f"The {name} causes a measurable effect on the system.\n"


def test_run_slice_ledger_and_summary(tmp_path):
    root = tmp_path
    # a file the registry knows → its canonical_urn is REUSED (kg-registry)
    (root / "reuse.txt").write_text(_marker_text("regulation"), encoding="utf-8")
    # a file the registry does NOT know → identity is MINTED
    (root / "mint.txt").write_text(_marker_text("device"), encoding="utf-8")

    registry = consume.Registry([
        {"original_path": "reuse.txt", "filename": "reuse.txt",
         "canonical_urn": "urn:dls:source:reuse-doc",
         "primary_topic": "TargetDomain", "jurisdiction": "EU", "detected_year": "2021"},
        # a registry row with NO bytes on disk → citation-only / skipped
        {"original_path": "absent.pdf", "filename": "absent.pdf",
         "canonical_urn": "urn:dls:source:absent-doc",
         "primary_topic": "TargetDomain", "jurisdiction": "EU", "detected_year": "2020"},
        # an off-domain registry row → excluded by the domain filter (also absent)
        {"original_path": "other.pdf", "filename": "other.pdf",
         "canonical_urn": "urn:dls:source:other-doc",
         "primary_topic": "OtherDomain", "jurisdiction": "US", "detected_year": "2019"},
    ])

    result = run_slice(registry, library="testlib", root=root,
                       domain_substring="TargetDomain", folder_for_index=root)
    ledger, summary = result["ledger"], result["summary"]

    by_rel = {e["relpath"]: e for e in ledger}
    # the off-domain absent row is filtered out of the slice
    assert set(by_rel) == {"reuse.txt", "mint.txt", "absent.pdf"}

    # reused file: processable, processed, reuses the registry canonical_urn
    assert by_rel["reuse.txt"]["pdf_status"] == "processable"
    assert by_rel["reuse.txt"]["status"] == "processed"
    assert by_rel["reuse.txt"]["provenance"] == "kg-registry"
    assert by_rel["reuse.txt"]["canonical_urn"] == "urn:dls:source:reuse-doc"
    assert by_rel["reuse.txt"]["n_claims"] >= 1

    # minted file: processable, processed, provenance minted, no reused canonical_urn
    assert by_rel["mint.txt"]["pdf_status"] == "processable"
    assert by_rel["mint.txt"]["provenance"] == "minted"
    assert by_rel["mint.txt"]["canonical_urn"] == ""

    # absent registry row: citation-only, skipped, zero claims
    assert by_rel["absent.pdf"]["pdf_status"] == "citation-only"
    assert by_rel["absent.pdf"]["status"] == "skipped"
    assert by_rel["absent.pdf"]["n_claims"] == 0
    assert by_rel["absent.pdf"]["provenance"] == "citation-only"

    # summary counts + convergence signal (over the 2 processed sources)
    assert summary["n_processable"] == 2
    assert summary["n_citation_only"] == 1
    assert summary["n_reuse"] == 1
    assert summary["n_mint"] == 1
    assert summary["reuse_rate"] == 0.5
    assert summary["mint_rate"] == 0.5


def test_run_slice_empty_slice_has_zero_rates(tmp_path):
    registry = consume.Registry([
        {"original_path": "x.pdf", "filename": "x.pdf",
         "canonical_urn": "urn:dls:source:x", "primary_topic": "Elsewhere"},
    ])
    result = run_slice(registry, library="lib", root=tmp_path,
                       domain_substring="NoSuchDomain", folder_for_index=tmp_path)
    assert result["ledger"] == []
    assert result["summary"]["reuse_rate"] == 0.0
    assert result["summary"]["mint_rate"] == 0.0
    assert result["summary"]["n_sources"] == 0
