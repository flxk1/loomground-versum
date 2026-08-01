import json

from versum.ingestion import acquire
from versum.ingestion.pipeline import audit, process
from versum.__main__ import main


PDF = b"%PDF-1.4\nbody\n%%EOF\n"


def test_recorded_pipeline_runs_end_to_end_and_resumes(tmp_path):
    inbox, review = tmp_path / "_inbox", tmp_path / "_review"
    src = tmp_path / "report.pdf"
    src.write_bytes(PDF)
    admitted = acquire.acquire(src, inbox)

    first = process(inbox, review)
    assert first["status"] == "complete" and first["resumed"] is False
    assert (review / admitted["artifact"]).exists()
    assert audit(inbox) == {
        "acquire": {"orphan_rows": [], "orphan_files": []},
        "provenance": {"orphan_sidecars": [], "missing_sidecars": []},
    }

    # First no-op pass records the post-route state; the next exact-state call resumes it.
    no_op = process(inbox, review)
    resumed = process(inbox, review)
    assert no_op["stages"]["route"]["counts"]["already_routed"] == 1
    assert resumed["resumed"] is True and resumed["run_id"] == no_op["run_id"]


def test_process_completes_with_workspace_housekeeping_files(tmp_path):
    inbox, review = tmp_path / "_inbox", tmp_path / "_review"
    src = tmp_path / "report.pdf"
    src.write_bytes(PDF)
    acquire.acquire(src, inbox)

    # A live macOS workspace inbox always carries these alongside the artifacts.
    (inbox / ".DS_Store").write_bytes(b"\x00")
    (inbox / "README.md").write_text("workspace notes", encoding="utf-8")
    (inbox / "organise.config.json").write_text("{}", encoding="utf-8")

    result = process(inbox, review)
    assert result["status"] == "complete"


def test_public_cli_ingest_process_and_audit(tmp_path, capsys):
    inbox, review = tmp_path / "_inbox", tmp_path / "_review"
    src = tmp_path / "note.txt"
    src.write_text("Alpha is defined as first.", encoding="utf-8")

    assert main(["ingest", str(src), "--inbox", str(inbox)]) == 0
    admitted = json.loads(capsys.readouterr().out)
    assert admitted["status"] == "acquired"
    assert main(["inbox-process", "--inbox", str(inbox), "--review", str(review)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "complete"
    assert main(["inbox-audit", "--inbox", str(inbox)]) == 0
