"""K3 falsifiers: declared authority and deletion-safe rebuilds."""
from pathlib import Path

from versum import sync
from versum.projections import (PROJECTION_DIR, SEARCH_FILE, projection_contract,
                                rebuild_projections, rebuild_search_projection)
from versum.store.retrieve import SearchIndex


def test_contract_protects_confirmed_curation():
    contract = projection_contract()
    assert "confirmed-curation" in contract["protected_inputs"]
    outputs = {path for spec in contract["projections"].values()
               for path in spec["outputs"]}
    assert ".versum/concepts.csv" not in outputs


def test_delete_search_projection_rebuild_preserves_queries(tmp_path):
    import csv
    domain = tmp_path / "by-domain" / "test"
    domain.mkdir(parents=True)
    with open(domain / "claims.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["canonical_urn", "library", "item_id",
                                                "text", "predicate", "dimension"])
        writer.writeheader()
        writer.writerow({"canonical_urn": "urn:test:1", "library": "lib",
                         "item_id": "claim-1", "text": "a widget causes motion",
                         "predicate": "causes", "dimension": "causal"})

    rebuild_search_projection(tmp_path)
    path = Path(tmp_path) / PROJECTION_DIR / SEARCH_FILE
    before = SearchIndex.load(path).search("widget motion", k=5)
    path.unlink()
    rebuild_search_projection(tmp_path)
    after = SearchIndex.load(path).search("widget motion", k=5)
    assert after == before


def test_full_projection_rebuild_into_empty_root_preserves_queries(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    (library / "source.txt").write_text(
        "A widget is defined as a device. A widget causes motion.\n", encoding="utf-8")
    source = tmp_path / "kg"
    cfg = {"kg_root": str(source), "profile_id": "generic", "libraries": [{
        "id": "lib", "root_path": str(library), "urn_namespace": "test",
        "registry_csv": None, "registry_path_prefix": "", "exclude_prefixes": ["_"],
    }]}
    sync.sync_once(cfg)
    rebuild_search_projection(source)
    before = SearchIndex.load(source / PROJECTION_DIR / SEARCH_FILE).search("widget", k=5)

    target = tmp_path / "rebuilt"
    rebuild_projections(source, target, cfg)
    after = SearchIndex.load(target / PROJECTION_DIR / SEARCH_FILE).search("widget", k=5)
    assert after == before
