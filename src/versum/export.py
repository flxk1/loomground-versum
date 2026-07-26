"""Graph export — project a ``.versum/`` workspace into viewer-consumable artifacts.

Three formats off one payload, all stdlib-only:

    json     the ``versum_graph/v1`` contract — nodes, edges, facets, fingerprints.
             Schema-versioned so external panels can version-gate before rendering.
    graphml  the same graph as GraphML XML for desktop tools (Gephi, Cytoscape);
             every node/edge attribute travels as a typed GraphML key.
    html     a self-contained offline viewer: the payload embedded in a single
             HTML file with an inline canvas renderer (no CDN, no dependency).

The payload is a PURE projection of the workspace files (claims.csv, sources.csv,
concepts.csv, semantic_edges.csv, fingerprints.json): the exporter invents no
vocabulary — facets are computed from the values actually present. Claims are joined
to their source by an implicit ``anchors`` edge (claim → source); that edge family is
``provenance`` to keep it distinct from the curated ``semantic`` fabric.
"""
from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.dom import minidom

from .store import graph as g

SCHEMA_VERSION = "versum_graph/v1"

# facet fields computed over the payload; the VALUES come from the data, never a list here
NODE_FACETS = ("kind",)
EDGE_FACETS = ("edge_type", "dimension", "verification", "edge_family")

_LABEL_MAX = 80


def _read_csv(path: Path) -> list[dict]:
    import csv
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _label(text: str, fallback: str) -> str:
    t = (text or "").strip().replace("\n", " ")
    if not t:
        return fallback
    return t if len(t) <= _LABEL_MAX else t[: _LABEL_MAX - 1] + "…"


def build_payload(folder) -> dict:
    """Project ``<folder>/.versum/`` into the ``versum_graph/v1`` payload."""
    v = Path(folder).resolve() / ".versum"
    if not v.is_dir():
        raise FileNotFoundError(f"no .versum workspace under {folder}")

    sources = _read_csv(v / "sources.csv")
    claims = g.load_claims(v / "claims.csv") if (v / "claims.csv").exists() else []
    concepts = g.load_concepts(v / "concepts.csv") if (v / "concepts.csv").exists() else []
    edges = g.load_edges(v / "semantic_edges.csv") if (v / "semantic_edges.csv").exists() else []
    fingerprints = {}
    fp_path = v / "fingerprints.json"
    if fp_path.exists():
        try:
            fingerprints = json.loads(fp_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fingerprints = {}
    manifest = {}
    mf_path = v / "index.json"
    if mf_path.exists():
        try:
            manifest = json.loads(mf_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}

    nodes: list[dict] = []
    node_ids: set[str] = set()

    # source paths are relative to the INDEXED folder, which the manifest records —
    # it differs from the workspace folder when the index was written with --out
    corpus_root = Path(manifest.get("folder") or folder).resolve()

    for s in sources:
        urn = s.get("source_urn", "")
        if not urn or urn in node_ids:
            continue
        node_ids.add(urn)
        name = Path(s.get("path", "")).name or urn.rsplit(":", 1)[-1]
        attrs = {k: s.get(k, "") for k in
                 ("path", "n_items", "profile", "provenance",
                  "library", "canonical_urn") if s.get(k)}
        rel = s.get("path", "")
        if rel:
            fp = Path(rel) if Path(rel).is_absolute() else corpus_root / rel
            try:
                if fp.exists():
                    attrs["file_url"] = fp.resolve().as_uri()
                    attrs["file_size"] = fp.stat().st_size
            except OSError:
                pass
        nodes.append({"id": urn, "kind": "source", "label": name, "attrs": attrs})

    for c in claims:
        cid = c.get("item_id", "")
        if not cid or cid in node_ids:
            continue
        node_ids.add(cid)
        nodes.append({"id": cid, "kind": "claim",
                      "label": _label(c.get("text", ""), cid),
                      "attrs": {k: c.get(k, "") for k in
                                ("source_urn", "text", "polarity", "dimension",
                                 "predicate", "modality", "quantification",
                                 "confidence", "verification", "span_start",
                                 "span_end", "profile") if c.get(k) not in ("", None)}})

    for cn in concepts:
        nid = cn.get("concept_id", "")
        if not nid or nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({"id": nid, "kind": "concept",
                      "label": _label(cn.get("label", ""), nid),
                      "attrs": {k: cn.get(k, "") for k in
                                ("domain", "definition", "status", "aliases",
                                 "catalogue_version") if cn.get(k)}})

    out_edges: list[dict] = []
    seen_edges: set[str] = set()

    # implicit provenance join: every claim anchors to its source
    for c in claims:
        src, dst = c.get("item_id", ""), c.get("source_urn", "")
        if not src or not dst or dst not in node_ids:
            continue
        eid = f"anchor:{src}"
        if eid in seen_edges:
            continue
        seen_edges.add(eid)
        out_edges.append({"id": eid, "src": src, "dst": dst,
                          "edge_type": "anchors", "edge_family": "provenance",
                          "dimension": c.get("dimension", ""),
                          "verification": c.get("verification", ""),
                          "confidence": c.get("confidence", "")})

    for e in edges:
        eid = e.get("edge_id", "")
        if not eid or eid in seen_edges:
            continue
        seen_edges.add(eid)
        out_edges.append({"id": eid, "src": e.get("src_id", ""),
                          "dst": e.get("dst_id", ""),
                          "edge_type": e.get("edge_type", ""),
                          "edge_family": e.get("edge_family", ""),
                          "dimension": e.get("dimension", ""),
                          "verification": e.get("verification", ""),
                          "confidence": e.get("confidence", ""),
                          "rationale": e.get("rationale", ""),
                          "semantic_role": e.get("semantic_role", "")})

    facets: dict[str, list] = {}
    for f in NODE_FACETS:
        facets[f] = sorted({n.get(f, "") for n in nodes if n.get(f)})
    for f in EDGE_FACETS:
        facets[f] = sorted({e.get(f, "") for e in out_edges if e.get(f)})

    return {"version": SCHEMA_VERSION,
            "folder": Path(folder).resolve().name,
            "profile": manifest.get("profile", ""),
            "counts": {"sources": sum(1 for n in nodes if n["kind"] == "source"),
                       "claims": sum(1 for n in nodes if n["kind"] == "claim"),
                       "concepts": sum(1 for n in nodes if n["kind"] == "concept"),
                       "edges": len(out_edges)},
            "nodes": nodes, "edges": out_edges,
            "facets": facets, "fingerprints": fingerprints}


# ── GraphML ──────────────────────────────────────────────────────

def _graphml_keys(payload) -> tuple[list[str], list[str]]:
    nkeys = sorted({k for n in payload["nodes"] for k in n["attrs"]} | {"kind", "label"})
    ekeys = sorted({k for e in payload["edges"] for k in e
                    if k not in ("id", "src", "dst") and e.get(k)})
    return nkeys, ekeys


def write_graphml(payload: dict, path) -> None:
    """Write the payload as GraphML with every attribute as a declared key."""
    ET.register_namespace("", "http://graphml.graphdrawing.org/xmlns")
    root = ET.Element("{http://graphml.graphdrawing.org/xmlns}graphml")
    nkeys, ekeys = _graphml_keys(payload)
    for k in nkeys:
        ET.SubElement(root, "key", id=f"n_{k}", **{"for": "node",
                      "attr.name": k, "attr.type": "string"})
    for k in ekeys:
        ET.SubElement(root, "key", id=f"e_{k}", **{"for": "edge",
                      "attr.name": k, "attr.type": "string"})
    graph = ET.SubElement(root, "graph", id=payload["folder"] or "versum",
                          edgedefault="directed")
    for n in payload["nodes"]:
        el = ET.SubElement(graph, "node", id=n["id"])
        values = {"kind": n["kind"], "label": n["label"], **n["attrs"]}
        for k, val in values.items():
            d = ET.SubElement(el, "data", key=f"n_{k}")
            d.text = str(val)
    for e in payload["edges"]:
        el = ET.SubElement(graph, "edge", id=e["id"], source=e["src"], target=e["dst"])
        for k in ekeys:
            if e.get(k):
                d = ET.SubElement(el, "data", key=f"e_{k}")
                d.text = str(e[k])
    pretty = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(
        indent="  ")
    Path(path).write_text(pretty, encoding="utf-8")


# ── HTML viewer ──────────────────────────────────────────────────

def write_html(payload: dict, path) -> None:
    """Write the self-contained offline viewer with the payload embedded."""
    from .viewer_template import VIEWER_HTML
    blob = json.dumps(payload, ensure_ascii=False)
    # </script> inside JSON strings would terminate the tag early — split it
    blob = blob.replace("</", "<\\/")
    Path(path).write_text(VIEWER_HTML.replace("__VERSUM_PAYLOAD__", blob),
                          encoding="utf-8")


def export(folder, fmt: str = "html", out=None) -> dict:
    """Export the folder's graph; returns a small report dict."""
    if fmt not in ("html", "json", "graphml"):
        raise ValueError(f"unknown export format: {fmt}")
    payload = build_payload(folder)
    if out is None:
        stem = Path(folder).resolve() / ".versum" / "graph"
        out = stem.with_suffix("." + fmt)
    out = Path(out)
    if fmt == "json":
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    elif fmt == "graphml":
        write_graphml(payload, out)
    elif fmt == "html":
        write_html(payload, out)
    else:
        raise ValueError(f"unknown export format: {fmt}")
    return {"status": "ok", "format": fmt, "out": str(out),
            "counts": payload["counts"]}
