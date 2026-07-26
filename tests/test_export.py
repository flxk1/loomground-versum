"""Graph export: versum_graph/v1 payload, GraphML, and the self-contained HTML viewer."""
import json
import csv
from xml.etree import ElementTree as ET

import pytest

from versum.store import graph as g
from versum.export import SCHEMA_VERSION, build_payload, export


def _workspace(tmp_path):
    """A tiny curated workspace: 1 source, 2 claims, 1 concept, 1 grounds edge."""
    v = tmp_path / ".versum"
    v.mkdir()
    with (v / "sources.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["source_urn", "path", "n_items", "unit_type",
                                           "profile", "provenance", "library",
                                           "canonical_urn"])
        w.writeheader()
        w.writerow({"source_urn": "urn:x:doc1", "path": "doc1.md", "n_items": "2",
                    "unit_type": "paragraph", "profile": "generic",
                    "provenance": "local", "library": "", "canonical_urn": ""})
    claims = [
        {"item_id": "c1", "source_urn": "urn:x:doc1", "text": "Heat causes expansion.",
         "polarity": "D", "dimension": "causal", "predicate": "causes",
         "verification": "candidate", "span_start": 0, "span_end": 22},
        {"item_id": "c2", "source_urn": "urn:x:doc1", "text": "Members must comply.",
         "polarity": "N", "dimension": "intentional", "predicate": "obliges",
         "verification": "candidate", "span_start": 23, "span_end": 43},
    ]
    g.save_claims(v / "claims.csv", claims, "generic")
    g.save_concepts(v / "concepts.csv", [
        {"concept_id": "thermal-expansion", "label": "Thermal expansion",
         "domain": "physics", "status": "confirmed"}])
    g.save_edges(v / "semantic_edges.csv", [
        {"edge_id": "e1", "src_id": "c1", "dst_id": "thermal-expansion",
         "edge_type": "grounds", "edge_family": "semantic", "dimension": "causal",
         "verification": "confirmed", "confidence": "0.9"}])
    (v / "fingerprints.json").write_text(json.dumps(
        {"urn:x:doc1": {"dim5": {"polarity": {"D": 1, "N": 1}}, "nd": {}}}),
        encoding="utf-8")
    (v / "index.json").write_text(json.dumps({"profile": "generic"}), encoding="utf-8")
    return tmp_path


def test_payload_is_a_pure_projection_of_the_workspace(tmp_path):
    payload = build_payload(_workspace(tmp_path))
    assert payload["version"] == SCHEMA_VERSION
    assert payload["counts"] == {"sources": 1, "claims": 2, "concepts": 1, "edges": 3}
    kinds = {n["id"]: n["kind"] for n in payload["nodes"]}
    assert kinds == {"urn:x:doc1": "source", "c1": "claim", "c2": "claim",
                     "thermal-expansion": "concept"}
    # claims join their source through the implicit provenance edge
    anchors = [e for e in payload["edges"] if e["edge_type"] == "anchors"]
    assert {(e["src"], e["dst"]) for e in anchors} == {
        ("c1", "urn:x:doc1"), ("c2", "urn:x:doc1")}
    assert all(e["edge_family"] == "provenance" for e in anchors)
    # facets are computed from the data, not invented
    assert payload["facets"]["dimension"] == ["causal", "intentional"]
    assert "grounds" in payload["facets"]["edge_type"]
    assert payload["fingerprints"]["urn:x:doc1"]["dim5"]["polarity"] == {"D": 1, "N": 1}


def test_export_graphml_declares_keys_and_survives_reparse(tmp_path):
    ws = _workspace(tmp_path)
    report = export(ws, "graphml")
    out = ws / ".versum" / "graph.graphml"
    assert report["status"] == "ok" and out.exists()
    root = ET.parse(out).getroot()
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    graph = root.find("g:graph", ns)
    assert len(graph.findall("g:node", ns)) == 4
    assert len(graph.findall("g:edge", ns)) == 3
    # every data key used by nodes/edges is declared up front
    declared = {k.get("id") for k in root.findall("g:key", ns)}
    used = {d.get("key") for el in graph.iter() for d in el.findall("g:data", ns)}
    assert used <= declared
    # attribute round-trip: the grounds edge keeps its dimension
    e1 = [e for e in graph.findall("g:edge", ns) if e.get("id") == "e1"][0]
    vals = {root.find(f"g:key[@id='{d.get('key')}']", ns).get("attr.name"): d.text
            for d in e1.findall("g:data", ns)}
    assert vals["dimension"] == "causal" and vals["edge_type"] == "grounds"


def test_export_html_is_self_contained_and_version_gated(tmp_path):
    ws = _workspace(tmp_path)
    export(ws, "html")
    html = (ws / ".versum" / "graph.html").read_text(encoding="utf-8")
    assert SCHEMA_VERSION in html                      # payload embedded + gate present
    assert "Heat causes expansion." in html
    assert "__VERSUM_PAYLOAD__" not in html            # token substituted
    assert "<script src=" not in html and "@import" not in html  # no external assets
    # a </script> inside claim text must not terminate the payload script tag
    assert html.count("</script>") == 1


def test_export_json_and_unknown_format(tmp_path):
    ws = _workspace(tmp_path)
    export(ws, "json")
    data = json.loads((ws / ".versum" / "graph.json").read_text(encoding="utf-8"))
    assert data["version"] == SCHEMA_VERSION
    with pytest.raises(ValueError):
        export(ws, "svg")


def test_export_needs_a_workspace(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_payload(tmp_path)


def test_source_nodes_carry_the_file_when_it_exists(tmp_path):
    _workspace(tmp_path)
    (tmp_path / "doc1.md").write_text("Heat causes expansion. Members must comply.",
                                      encoding="utf-8")
    payload = build_payload(tmp_path)
    src = next(n for n in payload["nodes"] if n["kind"] == "source")
    assert src["attrs"]["file_url"].startswith("file://")
    assert src["attrs"]["file_url"].endswith("/doc1.md")
    assert src["attrs"]["file_size"] > 0
    # the viewer renders it as a card with an open action
    out = tmp_path / "graph.html"
    export(tmp_path, "html", out)
    html = out.read_text(encoding="utf-8")
    assert "filecard" in html and "Open file" in html


def test_missing_files_yield_no_dead_links(tmp_path):
    payload = build_payload(_workspace(tmp_path))     # doc1.md never written
    src = next(n for n in payload["nodes"] if n["kind"] == "source")
    assert "file_url" not in src["attrs"]


def test_file_resolution_uses_the_manifest_corpus_root(tmp_path):
    # index written with --out: workspace lives apart from the corpus folder
    corpus = tmp_path / "corpus"; corpus.mkdir()
    (corpus / "doc1.md").write_text("x", encoding="utf-8")
    (tmp_path / "ws").mkdir()
    ws = _workspace(tmp_path / "ws")
    (ws / ".versum" / "index.json").write_text(
        json.dumps({"profile": "generic", "folder": str(corpus)}), encoding="utf-8")
    payload = build_payload(ws)
    src = next(n for n in payload["nodes"] if n["kind"] == "source")
    assert src["attrs"]["file_url"].endswith("/corpus/doc1.md")
