from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
DELEGATE = (
    REPO
    / "skills"
    / "loomground-knowledge-write"
    / "scripts"
    / "delegate_capture.py"
)
LIVE_CAPTURE = (
    REPO.parent
    / "editorial"
    / "loomground-editorial"
    / "skills"
    / "capture-to-kg"
    / "scripts"
    / "kg_capture.py"
)


def test_delegate_forwards_to_live_capture_writer(tmp_path: Path) -> None:
    if not LIVE_CAPTURE.is_file():
        pytest.skip("loomground-editorial capture-to-kg is an optional integration")
    spec = tmp_path / "spec.json"
    out = tmp_path / "drop"
    spec.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "title": "Delegation Teeth",
                        "authors": ["Release Test"],
                        "year": "2026",
                        "id_type": "doi",
                        "identifier": "10.1000/delegation",
                        "verification": "test fixture",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(DELEGATE),
            "--capture-script",
            str(LIVE_CAPTURE),
            "--spec",
            str(spec),
            "--outdir",
            str(out),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    result = report["results"][0]
    assert result["canonical_urn"] == "urn:dls:doi:10.1000%2Fdelegation"
    assert result["kind"] == "citation-stub"
    assert result["written"]
    sidecar = out / next(name for name in result["written"] if name.endswith(".metadata.json"))
    assert json.loads(sidecar.read_text(encoding="utf-8"))["manifest_notes"] == "capture-to-kg"


def test_delegate_fails_closed_without_canonical_writer(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(DELEGATE),
            "--capture-script",
            str(tmp_path / "missing.py"),
            "--spec",
            str(tmp_path / "spec.json"),
            "--outdir",
            str(tmp_path / "drop"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "capture-to-kg executable not found" in completed.stderr
    assert not (tmp_path / "drop").exists()
