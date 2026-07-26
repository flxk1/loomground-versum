"""Black-box smoke test for an installed Versum artifact."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(*args: str) -> subprocess.CompletedProcess[str]:
    executable = Path(sys.executable).with_name("versum")
    return subprocess.run([str(executable), *args], check=True, capture_output=True, text=True)


def main() -> int:
    from versum.ingestion import acquire, pipeline
    from versum.loomground import language_info

    assert callable(acquire.acquire)
    assert callable(pipeline.process)
    assert language_info()["language"] == "loomground"
    run("--help")
    for command in ("index", "capture", "capture-file", "validate-nd", "suggest",
                    "ingest", "inbox-process", "inbox-audit", "adapt"):
        run(command, "--help")
    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        source = base / "outside.md"
        target = base / "corpus"
        source.write_text("Alpha is defined as the first term.\n", encoding="utf-8")
        report = json.loads(run("capture-file", str(source), "--target", str(target)).stdout)
        assert report["status"] == "admitted"
        assert report["claim_count"] >= 0
        assert (target / ".versum" / "index.json").exists()
        observation = base / "observation.json"
        observation.write_text(json.dumps({
            "nodes": [
                {"id": "agent", "class": "actor"},
                {"id": "gate", "class": "gate"},
                {"id": "master", "class": "master"},
            ],
            "cords": [
                {"from": "agent", "to": "gate", "type": "authority"},
                {"from": "gate", "to": "master", "type": "egress"},
            ],
            "reservations": [],
        }), encoding="utf-8")
        adapter_out = base / "adapter-graph"
        adapted = json.loads(run(
            "adapt", "--adapter", "loomground", "--observation", str(observation),
            "--out", str(adapter_out),
        ).stdout)
        assert adapted["system"] == "loomground-governance"
        assert adapted["relations"] == 2
        assert (adapter_out / "relations.csv").exists()
    print("installed-artifact smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
