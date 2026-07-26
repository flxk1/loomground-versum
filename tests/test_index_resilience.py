"""More folder-indexer coverage — definitions.csv, skipped files, curation preservation.

Generic profile, plain-text inputs only (no PDF, no network).
"""
import csv
import json
from pathlib import Path

from versum.store.index import index_folder, DEFINITION_COLUMNS
from versum.store import graph as g
import versum.profiles  # noqa: F401 — register built-ins


def _corpus(root: Path):
    (root / "a.md").write_text(
        "'Chlorophyll' is defined as the green pigment. "
        "Sunlight causes the reaction every leaf performs.\n", encoding="utf-8")
    (root / "b.txt").write_text(
        "'Entropy' means disorder. Friction causes heat in any system.\n",
        encoding="utf-8")


def test_definitions_csv_columns_and_manifest_count(tmp_path):
    _corpus(tmp_path)
    manifest = index_folder(tmp_path, "generic")
    defs_path = tmp_path / ".versum" / "definitions.csv"
    assert defs_path.exists()

    with open(defs_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == DEFINITION_COLUMNS
        rows = list(reader)

    # chlorophyll + entropy were both quoted-and-defined
    slugs = {r["term_slug"] for r in rows}
    assert {"chlorophyll", "entropy"} <= slugs
    # manifest count equals the CSV row count
    assert manifest["n_definitions"] == len(rows)


def test_unsupported_file_is_skipped_not_indexed(tmp_path):
    _corpus(tmp_path)
    (tmp_path / "image.bin").write_bytes(b"\x00\x01binary not text")
    manifest = index_folder(tmp_path, "generic")

    assert any("image.bin" in s for s in manifest["skipped"])
    # the .bin never becomes a source
    sources = list(csv.DictReader(
        open(tmp_path / ".versum" / "sources.csv", newline="", encoding="utf-8")))
    assert all("image.bin" not in r["path"] for r in sources)
    assert manifest["n_sources"] == 2


def test_reindex_preserves_hand_written_curation(tmp_path):
    _corpus(tmp_path)
    index_folder(tmp_path, "generic")
    v = tmp_path / ".versum"

    # a curator hand-writes a concept + a grounds edge to a real claim
    g.save_concepts(v / "concepts.csv",
                    [g.Concept("energy-transfer", "Energy transfer", "science")])
    claims = g.load_claims(v / "claims.csv")
    first_item = claims[0]["item_id"]
    g.save_edges(v / "semantic_edges.csv",
                 [g.Edge("e1", first_item, "energy-transfer", "grounds")])

    # re-index: claims/sources/definitions regenerate, curation output survives
    manifest = index_folder(tmp_path, "generic")
    concepts = g.load_concepts(v / "concepts.csv")
    edges = g.load_edges(v / "semantic_edges.csv")
    assert any(c["concept_id"] == "energy-transfer" for c in concepts)
    assert any(e["dst_id"] == "energy-transfer" for e in edges)
    # definitions still regenerate on the re-run
    assert manifest["n_definitions"] >= 2
