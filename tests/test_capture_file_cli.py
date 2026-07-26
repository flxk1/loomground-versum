from __future__ import annotations

import json
from pathlib import Path

from versum.__main__ import main


def _run(capsys, *args):
    code = main(list(args))
    output = capsys.readouterr().out
    return code, json.loads(output)


def test_capture_file_external_source_and_machine_report(tmp_path, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    source = outside / "notes.md"
    source.write_text("Alpha is defined as the first term.\n", encoding="utf-8")
    target = tmp_path / "target"

    code, report = _run(capsys, "capture-file", str(source), "--target", str(target))

    assert code == 0
    assert report["status"] == "admitted"
    assert report["admitted"] is True
    assert Path(report["target_path"]).parent == target
    assert Path(report["target_path"]).read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert Path(report["stub_path"]).exists()
    assert Path(report["sidecar_path"]).exists()
    assert isinstance(report["claim_count"], int)
    assert isinstance(report["fingerprint"], dict)


def test_capture_file_duplicate_is_idempotent(tmp_path, capsys):
    source = tmp_path / "source.md"
    source.write_text("Beta causes gamma.\n", encoding="utf-8")
    target = tmp_path / "target"
    assert _run(capsys, "capture-file", str(source), "--target", str(target))[0] == 0

    code, report = _run(capsys, "capture-file", str(source), "--target", str(target))

    assert code == 0
    assert report["status"] == "duplicate"
    assert report["reason"] == "duplicate_hash"


def test_capture_file_basename_collision_is_safe(tmp_path, capsys):
    a = tmp_path / "a"; b = tmp_path / "b"; target = tmp_path / "target"
    a.mkdir(); b.mkdir(); target.mkdir()
    first = a / "same.md"; second = b / "same.md"
    first.write_text("Alpha is defined as the first term in this vocabulary.\n", encoding="utf-8")
    second.write_text("Delta is defined as the fourth term in this vocabulary.\n", encoding="utf-8")

    _, one = _run(capsys, "capture-file", str(first), "--target", str(target))
    _, two = _run(capsys, "capture-file", str(second), "--target", str(target))

    assert Path(one["target_path"]).name == "same.md"
    assert Path(two["target_path"]).name.endswith("-same.md")
    assert Path(one["target_path"]).read_text() != Path(two["target_path"]).read_text()


def test_capture_file_reports_input_errors(tmp_path, capsys):
    target = tmp_path / "target"
    cases = [
        (("missing.md", "--target", str(target)), "source_not_found", 3),
    ]
    unsupported = tmp_path / "source.bin"; unsupported.write_bytes(b"binary")
    empty = tmp_path / "empty.md"; empty.write_text("")
    valid = tmp_path / "valid.md"; valid.write_text("content")
    cases.extend([
        ((str(unsupported), "--target", str(target)), "unsupported_type", 4),
        ((str(empty), "--target", str(target)), "empty_source", 5),
        ((str(valid), "--target", str(target), "--profile", "missing"), "invalid_profile", 4),
    ])
    for args, error, expected_code in cases:
        code, report = _run(capsys, "capture-file", *args)
        assert code == expected_code
        assert report["status"] == "error"
        assert report["error"] == error


def test_capture_file_rejects_malformed_pdf(tmp_path, capsys):
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"not a pdf")
    code, report = _run(capsys, "capture-file", str(source), "--target", str(tmp_path / "target"))
    assert code == 5
    assert report["error"] == "extraction_failure"
