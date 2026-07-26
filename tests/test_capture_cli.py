from __future__ import annotations

import csv
import json

import pytest

from versum.__main__ import main
from versum.io.consume import REGISTRY_COLUMNS
from versum.write import load_registry


def _write_consume_registry(path, *, filename: str, canonical_urn: str) -> None:
    row = {column: "" for column in REGISTRY_COLUMNS}
    row.update({
        "source_id": "source-1",
        "canonical_urn": canonical_urn,
        "original_path": filename,
        "filename": filename,
    })
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_COLUMNS)
        writer.writeheader()
        writer.writerow(row)


def test_capture_cli_consumes_registry_and_records_library(tmp_path, capsys):
    folder = tmp_path / "library"
    folder.mkdir()
    source = folder / "registered.md"
    source.write_text("Alpha is defined as the first term.\n", encoding="utf-8")
    registry = tmp_path / "source_registry.csv"
    canonical_urn = "urn:kg:canonical:registered"
    _write_consume_registry(
        registry, filename=source.name, canonical_urn=canonical_urn,
    )

    code = main([
        "capture",
        str(folder),
        "--consume-registry",
        str(registry),
        "--library",
        "knowledge",
        "--namespace",
        "library-ns",
    ])

    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["index"]["n_kg_reused"] == 1
    assert report["index"]["library"] == "knowledge"
    assert report["index"]["namespace"] == "library-ns"
    [captured] = load_registry(folder)
    assert captured["urn"] == canonical_urn
    assert captured["canonical_urn"] == canonical_urn
    assert captured["library"] == "knowledge"


def test_capture_cli_namespace_mints_unregistered_source(tmp_path, capsys):
    folder = tmp_path / "library"
    folder.mkdir()
    (folder / "new.md").write_text("Beta causes gamma.\n", encoding="utf-8")

    assert main([
        "capture", str(folder), "--library", "knowledge", "--namespace", "library-ns",
    ]) == 0

    json.loads(capsys.readouterr().out)
    [captured] = load_registry(folder)
    assert captured["urn"].startswith("urn:library-ns:sha256:")
    assert captured["canonical_urn"] == ""
    assert captured["library"] == "knowledge"


def test_capture_help_documents_registry_and_library_options(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["capture", "--help"])

    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--consume-registry CSV" in help_text
    assert "--library ID" in help_text
    assert "--namespace NS" in help_text
