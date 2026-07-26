"""Inbox Pass 1-3 — provenance, year, route — proven on synthetic artifacts.

Gates (deterministic; no network, no LLM):

  P1  immutable URN         — the URN comes from content/canonical id; moving the shelved
                              file to the review queue does not change it (INV-1).
  P1b dedup on content      — two different filenames with identical bytes collapse to one
                              content URN; the second is a duplicate, not a second record.
  P1c quarantine            — an empty file and a .pdf without the %PDF header go to _failed/
                              with a reason and get no sidecar.
  P1d canonical wins        — a DOI-in-name file keys on its DOI urn, not a content hash.
  P2  year, never mtime     — a recently-written file with an old year in its title resolves
                              to the old year; a signal-free file is 'undated'; the filesystem
                              time is never the answer.
  P3  review-only + no-op   — every registered artifact routes to _review/ (never a domain
                              folder); a re-run is a no-op; the sidecar travels with the file.
  P3b consolidation dry-run — an existing inbox folder yields a plan and is not modified.
  AUD both-directions       — after each pass, no orphan sidecars and no missing sidecars.
"""
from pathlib import Path

from versum.ingestion import acquire as A
from versum.ingestion import provenance as P
from versum.ingestion import year as Y
from versum.ingestion import route as R

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _drop(inbox: Path, name: str, body: bytes) -> str:
    """Acquire one local file into the inbox (Pass 0), so the ledger is populated."""
    src = inbox.parent / name
    src.write_bytes(body)
    return A.acquire(str(src), inbox, "generic", fetcher=A.NullFetcher())["artifact"]


# ── P1 — immutable URN survives a move to the review queue (INV-1) ──
def test_p1_urn_immutable_under_move(tmp_path):
    inbox = tmp_path / "_inbox"
    artifact = _drop(inbox, "report-alpha.pdf", PDF + b"alpha")
    res = P.provenance(inbox, "generic")
    assert res["counts"]["registered"] == 1
    urn_before = P.read_sidecar(inbox, artifact)["canonical_urn"]
    assert ":sha256:" in urn_before                      # content-addressed, not path-derived

    review = tmp_path / "_review"
    R.route_to_review(inbox, review)
    urn_after = P.read_sidecar(review, artifact)["canonical_urn"]
    assert urn_after == urn_before                        # move did not re-mint


# ── P1b — identical bytes, different names → one content URN ──
def test_p1b_content_dedup_end_to_end(tmp_path):
    """Identical bytes collapse to one record. Acquire (Pass 0) catches it on the content URN,
    so only the first survives to provenance — exactly one sidecar is written."""
    inbox = tmp_path / "_inbox"
    (tmp_path / "one.pdf").write_bytes(PDF + b"same-bytes")
    (tmp_path / "two.pdf").write_bytes(PDF + b"same-bytes")
    r1 = A.acquire(str(tmp_path / "one.pdf"), inbox, "generic", fetcher=A.NullFetcher())
    r2 = A.acquire(str(tmp_path / "two.pdf"), inbox, "generic", fetcher=A.NullFetcher())
    assert r1["status"] == "acquired"
    assert r2["status"] == "duplicate" and r2["urn"] == r1["urn"]   # same content URN
    res = P.provenance(inbox, "generic")
    assert res["counts"]["registered"] == 1
    assert len(list(inbox.glob("*" + P.SIDE))) == 1


def test_p1b_provenance_dedup_safety_net(tmp_path):
    """If two acquired rows ever share a URN (e.g. a file and its already-fetched URL twin),
    provenance registers the first and marks the second a duplicate — it never double-records."""
    inbox = tmp_path / "_inbox"
    inbox.mkdir(parents=True)
    (inbox / "a.pdf").write_bytes(PDF + b"twinned")
    (inbox / "b.pdf").write_bytes(PDF + b"twinned")          # identical bytes → identical URN
    from versum.identity.core import deterministic_identity
    from versum.profile import get_profile
    urn = deterministic_identity(inbox / "a.pdf", get_profile("generic"))[0]
    rows = [{"input": n, "kind": "file", "urn": urn, "identity_method": "content-sha256",
             "status": "acquired", "artifact": n, "source_url": "", "content_sha256": ""}
            for n in ("a.pdf", "b.pdf")]
    A.save_log(inbox, rows)
    res = P.provenance(inbox, "generic")
    assert res["counts"]["registered"] == 1 and res["counts"]["duplicate"] == 1
    dup = [o for o in res["outcomes"] if o["outcome"] == "duplicate"][0]
    assert dup["duplicate_of"] == "a.pdf"
    assert A.audit(inbox) == {"orphan_rows": [], "orphan_files": []}
    assert P.audit(inbox) == {"orphan_sidecars": [], "missing_sidecars": []}


# ── P1c — corrupt/empty → _failed/, no sidecar ──
def test_p1c_quarantine(tmp_path):
    inbox = tmp_path / "_inbox"
    empty = _drop(inbox, "empty.pdf", b"")
    broken = _drop(inbox, "not-really.pdf", b"this is not a pdf at all")
    res = P.provenance(inbox, "generic")
    assert res["counts"]["failed"] == 2
    assert (inbox / "_failed" / empty).exists()
    assert (inbox / "_failed" / broken).exists()
    assert not P.sidecar_path(inbox, empty).exists()
    reasons = (inbox / "_failed" / "_failed_log.csv").read_text()
    assert "empty" in reasons and "not-a-pdf" in reasons


# ── P1d — a canonical id in the name beats the content hash ──
def test_p1d_canonical_wins(tmp_path):
    # an arXiv id survives in a filename (a DOI's slash cannot); it must beat the content hash.
    inbox = tmp_path / "_inbox"
    artifact = _drop(inbox, "2401.12345.pdf", PDF + b"body")
    P.provenance(inbox, "generic")
    sc = P.read_sidecar(inbox, artifact)
    assert sc["identity_method"] == "arxiv"
    assert sc["canonical_urn"] == "urn:kg:arxiv:2401.12345"
    assert sc["provenance_level"] == "canonical"


# ── P2 — year from the title, never the filesystem mtime ──
def test_p2_year_never_mtime(tmp_path):
    inbox = tmp_path / "_inbox"
    artifact = _drop(inbox, "annual-review-2007.pdf", PDF + b"old content, fresh file")
    P.provenance(inbox, "generic")
    out = Y.apply_year(inbox)
    row = out["outcomes"][0]
    assert row["year"] == "2007"                          # from the filename, not this year
    assert row["method"] in ("title", "filename")
    assert P.read_sidecar(inbox, artifact)["year"] == "2007"


def test_p2_undated_is_first_class(tmp_path):
    inbox = tmp_path / "_inbox"
    artifact = _drop(inbox, "no-date-here.pdf", PDF + b"x")
    P.provenance(inbox, "generic")
    Y.apply_year(inbox)
    assert P.read_sidecar(inbox, artifact)["year"] == "undated"


def test_p2_canonical_id_year_hook(tmp_path):
    # a canonical id resolves the year via the injected resolver, ahead of any text signal.
    inbox = tmp_path / "_inbox"
    artifact = _drop(inbox, "2019.55555.pdf", PDF + b"y")
    P.provenance(inbox, "generic")

    def id_year(scheme, ident):
        return "2019" if scheme == "arxiv" else None

    Y.apply_year(inbox, id_year=id_year)
    sc = P.read_sidecar(inbox, artifact)
    assert sc["year"] == "2019" and sc["year_method"] == "canonical-id"


# ── P3 — route only to _review, and re-run is a no-op ──
def test_p3_route_review_only_and_idempotent(tmp_path):
    inbox = tmp_path / "_inbox"
    review = tmp_path / "_review"
    a = _drop(inbox, "a.pdf", PDF + b"a")
    b = _drop(inbox, "b.pdf", PDF + b"b")
    P.provenance(inbox, "generic")
    r1 = R.route_to_review(inbox, review)
    assert r1["counts"]["routed"] == 2
    assert (review / a).exists() and (review / (a + ".metadata.json")).exists()
    assert (review / b).exists()
    assert not (inbox / a).exists()                 # left the inbox
    # nothing created that looks like a domain shelf — review is the only destination
    assert {p.name for p in tmp_path.iterdir() if p.is_dir()} == {"_inbox", "_review"}
    r2 = R.route_to_review(inbox, review)
    assert r2["counts"]["routed"] == 0                    # re-drop is a no-op


def test_p3_resumes_interrupted_artifact_then_sidecar_move(tmp_path):
    inbox, review = tmp_path / "_inbox", tmp_path / "_review"
    artifact = _drop(inbox, "resume.pdf", PDF + b"resume")
    P.provenance(inbox)
    review.mkdir()
    (inbox / artifact).replace(review / artifact)  # simulate interruption between two moves
    result = R.route_to_review(inbox, review)
    assert result["counts"]["already_routed"] == 1
    assert (review / (artifact + P.SIDE)).exists()
    assert A.load_log(inbox)[0]["status"] == "review"
    assert A.audit(inbox) == {"orphan_rows": [], "orphan_files": []}


# ── P3b — consolidation is a dry run that moves nothing ──
def test_p3b_consolidation_plan_dry_run(tmp_path):
    old = tmp_path / "old_inbox"
    (old / "sub").mkdir(parents=True)
    (old / "keep-me.pdf").write_bytes(PDF)
    (old / "keep-me.pdf.metadata.json").write_text('{"canonical_urn": "urn:kg:x"}')  # paired sidecar
    (old / "sub" / "nested.pdf").write_bytes(PDF)
    (old / "_infra.txt").write_text("skip")
    plan = R.consolidation_plan([old], tmp_path / "migration_plan.csv")
    names = {r["filename"] for r in plan}
    assert names == {"keep-me.pdf", "nested.pdf"}         # _infra AND the sidecar excluded
    assert all(r["proposed_action"] == "acquire" for r in plan)
    ks = [r for r in plan if r["filename"] == "keep-me.pdf"][0]
    assert ks["has_sidecar"] is True                      # its sidecar is flagged, not re-acquired
    assert (old / "keep-me.pdf").exists()                 # source untouched
    assert (tmp_path / "migration_plan.csv").exists()


# ── AUD — both-directions integrity after the passes ──
def test_audit_clean_after_passes(tmp_path):
    inbox = tmp_path / "_inbox"
    _drop(inbox, "doc.pdf", PDF + b"c")
    P.provenance(inbox, "generic")
    a = P.audit(inbox)
    assert a == {"orphan_sidecars": [], "missing_sidecars": []}
