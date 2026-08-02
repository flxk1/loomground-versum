"""Bytes-arrive-for-an-existing-stub pairing (scripts/operations/pair_stub_bytes.py).

A PDF that turns up for a source already present as a citation stub must be filed
under the STUB's canonical_urn (identity_method "sidecar-pairing") — never minted a
fresh identity — and an ambiguous stub match must be surfaced, not guessed. The final
test drives the real sync pass over a paired corpus and asserts zero mints.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

from versum import sync

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "operations" / "pair_stub_bytes.py"
_spec = importlib.util.spec_from_file_location("pair_stub_bytes", _SCRIPT)
psb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(psb)

_FIXTURE_PDF = Path(__file__).parent / "fixtures" / "pdf" / "single-line-control.pdf"

STUB_URN = "urn:dls:source:beschlussempfehlung-ki-mig"
STUB_SIDECAR = {
    "source_id": "",
    "title": "Beschlussempfehlung und Bericht des Digitalausschusses zum KI-MIG",
    "year": "2026",
    "download_url": "https://dserver.bundestag.de/btd/21/064/2106407.pdf",
    "canonical_urn": STUB_URN,
    "identifier": "BT-Drs. 21/6407",
    "pdf_status": "unavailable",
}


def _corpus(tmp_path: Path, sidecar_overrides: dict | None = None) -> dict:
    """A library with one shelf holding one citation stub; returns the sync config."""
    library = tmp_path / "library"
    shelf = library / "ai_act_and_regulation" / "2026"
    shelf.mkdir(parents=True)
    stub = shelf / "2026-bundestag-beschlussempfehlung-ki-mig.md"
    stub.write_text("# Beschlussempfehlung\n\n- Canonical URN: " + STUB_URN + "\n",
                    encoding="utf-8")
    side = dict(STUB_SIDECAR, **(sidecar_overrides or {}))
    (shelf / (stub.name + ".metadata.json")).write_text(
        json.dumps(side, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "kg_root": str(tmp_path / "kg"), "profile_id": "generic",
        "libraries": [{"id": "lib", "root_path": str(library),
                       "urn_namespace": "test", "registry_csv": None}],
    }), encoding="utf-8")
    return sync.load_config(cfg_path)


def _arriving_pdf(tmp_path: Path, name: str = "2026 - bt-drs 21-6407 beschlussempfehlung.pdf") -> Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir(exist_ok=True)
    pdf = inbox / name
    pdf.write_bytes(_FIXTURE_PDF.read_bytes())
    return pdf


def test_dry_run_matches_by_identifier_and_writes_nothing(tmp_path):
    cfg = _corpus(tmp_path)
    pdf = _arriving_pdf(tmp_path)
    shelf = Path(cfg["libraries"][0]["root_path"]) / "ai_act_and_regulation" / "2026"
    before = sorted(p.name for p in shelf.iterdir())

    plan = psb.plan_pairs(cfg, [str(pdf)])

    assert plan["clean"]
    [entry] = plan["pairs"]
    assert entry["status"] == "pair"
    assert entry["match_method"] == "identifier"
    assert entry["stub"]["canonical_urn"] == STUB_URN
    assert Path(entry["writes"]["file_pdf"]).parent == shelf
    # plan is read-only
    assert sorted(p.name for p in shelf.iterdir()) == before


def test_apply_files_pdf_under_stub_urn_and_upgrades_stub_sidecar(tmp_path):
    cfg = _corpus(tmp_path)
    pdf = _arriving_pdf(tmp_path)
    plan = psb.plan_pairs(cfg, [str(pdf)], source_url="https://example.org/a.pdf")

    psb.apply_pairs(plan)

    [entry] = plan["pairs"]
    assert entry["status"] == "paired"
    filed = Path(entry["writes"]["file_pdf"])
    assert filed.read_bytes() == pdf.read_bytes()  # copied, original untouched
    assert pdf.exists()

    side = json.loads(Path(entry["writes"]["write_sidecar"]).read_text(encoding="utf-8"))
    assert side["canonical_urn"] == STUB_URN
    assert side["identity_method"] == "sidecar-pairing"
    assert side["provenance_level"] == "canonical"
    assert side["sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert side["source_file"] == filed.name
    assert side["source_url"] == "https://example.org/a.pdf"
    assert "no new identity minted" in side["identity_note"]

    stub_side = json.loads(Path(entry["writes"]["update_stub_sidecar"]).read_text(encoding="utf-8"))
    assert stub_side["pdf_status"] == "available"
    assert stub_side["pdf_file"] == filed.name
    # the rest of the stub sidecar survives untouched
    assert stub_side["identifier"] == STUB_SIDECAR["identifier"]
    assert stub_side["title"] == STUB_SIDECAR["title"]


def test_source_url_defaults_to_stub_download_url(tmp_path):
    cfg = _corpus(tmp_path)
    plan = psb.plan_pairs(cfg, [str(_arriving_pdf(tmp_path))])
    [entry] = plan["pairs"]
    assert entry["_sidecar"]["source_url"] == STUB_SIDECAR["download_url"]


def test_ambiguous_match_is_refused_even_on_apply(tmp_path):
    cfg = _corpus(tmp_path)
    # a second stub with the SAME identifier on another shelf
    shelf2 = Path(cfg["libraries"][0]["root_path"]) / "eu_digital_regulation" / "2026"
    shelf2.mkdir(parents=True)
    twin = shelf2 / "2026-twin-stub.md"
    twin.write_text("# Twin\n", encoding="utf-8")
    (shelf2 / (twin.name + ".metadata.json")).write_text(
        json.dumps(dict(STUB_SIDECAR, canonical_urn="urn:dls:source:twin")) + "\n",
        encoding="utf-8")
    pdf = _arriving_pdf(tmp_path)

    plan = psb.plan_pairs(cfg, [str(pdf)])
    [entry] = plan["pairs"]
    assert entry["status"] == "ambiguous"
    assert not plan["clean"]
    assert {c["canonical_urn"] for c in entry["candidates"]} == {STUB_URN, "urn:dls:source:twin"}

    psb.apply_pairs(plan)  # must be a no-op for non-"pair" entries
    assert entry["status"] == "ambiguous"
    assert not any(p.suffix == ".pdf" for p in shelf2.iterdir())

    # --urn resolves the ambiguity to exactly one stub
    plan = psb.plan_pairs(cfg, [str(pdf)], urn="urn:dls:source:twin")
    [entry] = plan["pairs"]
    assert entry["status"] == "pair"
    assert entry["match_method"] == "urn"
    assert entry["stub"]["canonical_urn"] == "urn:dls:source:twin"


def test_no_match_reports_instead_of_minting(tmp_path):
    cfg = _corpus(tmp_path)
    pdf = _arriving_pdf(tmp_path, name="2030 - entirely unrelated dossier.pdf")
    plan = psb.plan_pairs(cfg, [str(pdf)])
    [entry] = plan["pairs"]
    assert entry["status"] == "no-match"
    assert not plan["clean"]


def test_already_paired_stub_refuses_second_file_but_rerun_is_idempotent(tmp_path):
    cfg = _corpus(tmp_path)
    pdf = _arriving_pdf(tmp_path)
    plan = psb.plan_pairs(cfg, [str(pdf)])
    psb.apply_pairs(plan)

    # the same bytes again → clean no-op
    plan2 = psb.plan_pairs(cfg, [str(pdf)])
    [entry] = plan2["pairs"]
    assert entry["status"] == "already-filed"
    assert plan2["clean"]

    # different bytes claiming the same stub → refused
    other = _arriving_pdf(tmp_path, name="2026 - bt-drs 21-6407 second copy.pdf")
    other.write_bytes(other.read_bytes() + b"\n%extra\n")
    plan3 = psb.plan_pairs(cfg, [str(other)])
    [entry] = plan3["pairs"]
    assert entry["status"] == "already-paired"
    assert not plan3["clean"]


def test_overlong_filename_is_refused(tmp_path):
    cfg = _corpus(tmp_path)
    # 245 bytes: the OS can create the PDF, but its ".metadata.json" sidecar name
    # would exceed the 255-byte limit — exactly the window the guard covers.
    pdf = _arriving_pdf(tmp_path, name="2026 - bt-drs 21-6407 " + "x" * 219 + ".pdf")
    plan = psb.plan_pairs(cfg, [str(pdf)])
    [entry] = plan["pairs"]
    assert entry["status"] == "name-too-long"
    assert not plan["clean"]


def test_sync_indexes_paired_pdf_under_stub_urn_with_zero_mints(tmp_path):
    cfg = _corpus(tmp_path)
    pdf = _arriving_pdf(tmp_path)
    plan = psb.plan_pairs(cfg, [str(pdf)])
    psb.apply_pairs(plan)

    report = sync.sync_once(cfg)
    [lib] = report["libraries"]
    assert lib["mint"] == 0
    assert lib["errors"] == []

    src_csv = (Path(cfg["kg_root"]) / "by-domain" / "ai_act_and_regulation" / "sources.csv")
    rows = list(csv.DictReader(src_csv.open(newline="", encoding="utf-8")))
    [row] = [r for r in rows if r["path"].endswith(".pdf")]
    assert row["canonical_urn"] == STUB_URN
    assert row["provenance"] == "kg-canonical"
    # the stub itself is provenance-only — it never became a second source
    assert all(not r["path"].endswith(".md") for r in rows)
