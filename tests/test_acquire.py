"""KB-1.2 — Pass 0 acquire: file + URL intake, identity fixed at intake.

The four gates, run from the engine side:

  G1  DOI-in-URL wins        — a DOI URL registers under its DOI urn, fetch or no fetch.
  G2  unreachable != lost     — an unreachable no-DOI URL becomes citation-only + a
                                _pending_fetch/ marker; re-submitting is a no-op.
  G3  fetch-boundary          — a DOI registered citation-only keeps its DOI urn when the
                                artifact later arrives; the content hash is recorded
                                additively (identity not replaced) — an upgrade, not a re-mint.
  G4  both-directions audit   — every ledger row has its artifact/citation on disk and vice
                                versa; no orphans either way.

Network is a fake; nothing hits the wire. Deterministic; no LLM.
"""
import hashlib
from pathlib import Path

import pytest

from versum.ingestion import acquire as A
from versum.ingestion import provenance as P


class FakeFetcher(A.Fetcher):
    """Reachable URLs return bytes; anything not in the map is unreachable (None)."""

    def __init__(self, responses):
        self.responses = responses

    def fetch(self, url):
        return self.responses.get(url)


DOI_URL = "https://doi.org/10.1000/xyz123"
DOI_URN = "urn:kg:doi:10.1000/xyz123"


# ── G1 — DOI in the URL wins, fetch or no fetch ──────────────────
def test_g1_doi_url_no_fetch(tmp_path):
    r = A.acquire(DOI_URL, tmp_path, "generic", fetcher=A.NullFetcher())
    assert r["urn"] == DOI_URN and r["method"] == "doi"
    assert r["status"] == "citation-only"


def test_g1_doi_url_with_fetch(tmp_path):
    f = FakeFetcher({DOI_URL: b"%PDF-1.4 fake body\n"})
    r = A.acquire(DOI_URL, tmp_path, "generic", fetcher=f)
    assert r["urn"] == DOI_URN and r["method"] == "doi"      # DOI beats content hash
    assert r["status"] == "acquired"
    assert (tmp_path / r["artifact"]).exists()


# ── G2 — unreachable, no DOI -> citation-only + pending; re-submit no-op ──
def test_g2_unreachable_becomes_citation_and_is_idempotent(tmp_path):
    url = "https://example.org/some/report-with-no-id"
    r1 = A.acquire(url, tmp_path, "generic", fetcher=A.NullFetcher())
    assert r1["status"] == "citation-only"
    assert r1["urn"].startswith("urn:kg:url:")
    marker = A._citation_path(tmp_path, r1["urn"])
    assert marker.exists()                                   # not lost
    n_rows = len(A.load_log(tmp_path))
    r2 = A.acquire(url, tmp_path, "generic", fetcher=A.NullFetcher())
    assert r2["status"] == "duplicate"                        # re-submit is a no-op
    assert len(A.load_log(tmp_path)) == n_rows


# ── G3 — fetch-boundary: citation-only DOI, then the artifact arrives ──
def test_g3_citation_then_artifact_same_urn_additive_hash(tmp_path):
    # (a) no bytes yet -> citation-only, DOI urn, no content hash. (This is the path that
    #     used to CRASH before the identity guard: a no-bytes source resolving cleanly.)
    r1 = A.acquire(DOI_URL, tmp_path, "generic", fetcher=A.NullFetcher())
    assert r1["status"] == "citation-only" and r1["urn"] == DOI_URN
    row = next(x for x in A.load_log(tmp_path) if x["urn"] == DOI_URN)
    assert row["content_sha256"] == ""                        # nothing to hash yet

    # (b) the artifact arrives -> UPGRADE in place: same urn, content hash added additively.
    f = FakeFetcher({DOI_URL: b"the real pdf bytes\n"})
    r2 = A.acquire(DOI_URL, tmp_path, "generic", fetcher=f)
    assert r2["status"] == "upgraded"
    assert r2["urn"] == DOI_URN                               # identity unchanged across the boundary
    row = next(x for x in A.load_log(tmp_path) if x["urn"] == DOI_URN)
    assert row["identity_method"] == "doi"                    # still the canonical id, not a hash
    assert row["content_sha256"] != ""                        # hash recorded ADDITIVELY
    assert row["status"] == "acquired"
    assert not A._citation_path(tmp_path, DOI_URN).exists()   # pending marker cleared
    assert len([x for x in A.load_log(tmp_path) if x["urn"] == DOI_URN]) == 1  # no duplicate row


# ── local file intake ────────────────────────────────────────────
def test_file_intake_content_hash_and_dedup(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    inbox = tmp_path / "_inbox"
    f = src / "plain-note.txt"; f.write_bytes(b"Alpha is defined as first.\n")
    r1 = A.acquire(f, inbox, "generic")
    assert r1["status"] == "acquired" and r1["urn"].startswith("urn:kg:sha256:")
    assert (inbox / r1["artifact"]).exists()                  # content-addressed name
    r2 = A.acquire(f, inbox, "generic")                       # same bytes -> dedup
    assert r2["status"] == "duplicate"


# ── regression: basename collision must not clobber / orphan (review #1 + #2) ──
def test_same_basename_different_content_no_collision(tmp_path):
    inbox = tmp_path / "_inbox"
    d1 = tmp_path / "a"; d1.mkdir(); d2 = tmp_path / "b"; d2.mkdir()
    f1 = d1 / "report.pdf"; f1.write_bytes(b"document ONE unique bytes\n")
    f2 = d2 / "report.pdf"; f2.write_bytes(b"document TWO unique bytes\n")
    r1 = A.acquire(f1, inbox, "generic")
    r2 = A.acquire(f2, inbox, "generic")
    assert r1["urn"] != r2["urn"]                             # distinct identities
    assert r1["artifact"] != r2["artifact"]                  # distinct files on disk
    assert (inbox / r1["artifact"]).read_bytes() == b"document ONE unique bytes\n"
    assert (inbox / r2["artifact"]).read_bytes() == b"document TWO unique bytes\n"  # not clobbered
    a = A.audit(inbox)
    assert a["orphan_rows"] == [] and a["orphan_files"] == []


def test_url_content_dup_different_name_no_orphan(tmp_path):
    body = b"identical body, no doi\n"
    f = FakeFetcher({"https://a.org/x.pdf": body, "https://b.org/y.pdf": body})
    r1 = A.acquire("https://a.org/x.pdf", tmp_path, "generic", fetcher=f)
    r2 = A.acquire("https://b.org/y.pdf", tmp_path, "generic", fetcher=f)
    assert r1["status"] == "acquired" and r2["status"] == "duplicate"
    assert r1["urn"] == r2["urn"]                             # same content -> same urn
    assert A.audit(tmp_path)["orphan_files"] == []           # no stray artifact from the dup


@pytest.mark.parametrize("encoded_name", [
    "%2e%2e%2fescape.pdf",
    "%2e%2e%5cescape.pdf",
    "%252e%252e%252fescape.pdf",
    "%252e%252e%255cescape.pdf",
    "%2ftmp%2fescape.pdf",
    "C%3a%5cescape.pdf",
    "bad%00name.pdf",
])
def test_url_artifact_name_rejects_encoded_path_forms(tmp_path, encoded_name):
    inbox = tmp_path / "_inbox"
    url = f"https://example.org/{encoded_name}"

    with pytest.raises(ValueError):
        A.acquire(url, inbox, fetcher=FakeFetcher({url: b"hostile body"}))

    assert not (tmp_path / "escape.pdf").exists()
    assert A.load_log(inbox) == []


def test_url_artifact_name_keeps_ordinary_decoded_filename(tmp_path):
    url = "https://example.org/Annual%20Report%202026.pdf"
    result = A.acquire(url, tmp_path, fetcher=FakeFetcher({url: b"ordinary body"}))

    assert result["status"] == "acquired"
    assert result["artifact"].endswith("-Annual Report 2026.pdf")
    assert (tmp_path / result["artifact"]).read_bytes() == b"ordinary body"


def test_url_artifact_destination_rejects_symlink_escape(tmp_path):
    inbox = tmp_path / "_inbox"
    outside = tmp_path / "outside.pdf"
    body = b"must stay in inbox"
    sha = hashlib.sha256(body).hexdigest()
    name = f"{sha[:12]}-report.pdf"
    inbox.mkdir()
    (inbox / name).symlink_to(outside)
    url = "https://example.org/report.pdf"

    with pytest.raises(ValueError, match="escapes the configured inbox"):
        A.acquire(url, inbox, fetcher=FakeFetcher({url: body}))

    assert not outside.exists()
    assert A.load_log(inbox) == []


# ── G4 — mixed batch, both-directions audit clean ────────────────
def test_g4_mixed_batch_audit_clean(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    inbox = tmp_path / "_inbox"
    doc = src / "10.5555%2Fabc.pdf"; doc.write_bytes(b"a doi-named file\n")   # canonical file
    plain = src / "notes.md"; plain.write_bytes(b"Beta causes gamma.\n")       # content-hash file
    f = FakeFetcher({DOI_URL: b"fetched doi pdf\n"})                            # reachable DOI url
    unreachable = "https://example.net/lost/thing"                             # citation-only

    A.acquire(doc, inbox, "generic")
    A.acquire(plain, inbox, "generic")
    A.acquire(DOI_URL, inbox, "generic", fetcher=f)
    A.acquire(unreachable, inbox, "generic", fetcher=A.NullFetcher())

    rows = A.load_log(inbox)
    assert len(rows) == 4
    methods = {r["identity_method"] for r in rows}
    assert "doi" in methods and "content-sha256" in methods and "url-slug" in methods

    a = A.audit(inbox)
    assert a["orphan_rows"] == [] and a["orphan_files"] == []


def test_canonical_url_identity_survives_provenance(tmp_path):
    f = FakeFetcher({DOI_URL: b"%PDF-1.4\n%%EOF\n"})
    acquired = A.acquire(DOI_URL, tmp_path, "generic", fetcher=f)
    P.provenance(tmp_path, "generic")
    sidecar = P.read_sidecar(tmp_path, acquired["artifact"])
    assert sidecar["canonical_urn"] == DOI_URN
    assert sidecar["identity_method"] == "doi"
    assert sidecar["sha256"]


def test_no_id_citation_upgrades_with_explicit_alias(tmp_path):
    url = "https://example.org/report-with-no-id"
    pending = A.acquire(url, tmp_path, "generic", fetcher=A.NullFetcher())
    fetched = A.acquire(url, tmp_path, "generic",
                        fetcher=FakeFetcher({url: b"fetched body"}))
    assert fetched["status"] == "upgraded"
    rows = A.load_log(tmp_path)
    assert len(rows) == 1
    assert rows[0]["previous_urn"] == pending["urn"]
    assert rows[0]["urn"] == fetched["urn"]
    assert not A._citation_path(tmp_path, pending["urn"]).exists()
    assert A.audit(tmp_path) == {"orphan_rows": [], "orphan_files": []}


def test_quarantine_updates_authoritative_ledger(tmp_path):
    src = tmp_path / "broken.pdf"
    inbox = tmp_path / "_inbox"
    src.write_bytes(b"not a pdf")
    acquired = A.acquire(src, inbox)
    P.provenance(inbox)
    row = A.load_log(inbox)[0]
    assert row["status"] == "failed"
    assert row["failure_reason"] == "not-a-pdf"
    assert Path(row["quarantine_path"]).name == acquired["artifact"]
    assert A.audit(inbox) == {"orphan_rows": [], "orphan_files": []}
    assert P.audit(inbox) == {"orphan_sidecars": [], "missing_sidecars": []}

    row["quarantine_path"] = ""
    A.save_log(inbox, [row])
    assert A.audit(inbox)["orphan_rows"] == [row["urn"]]


def test_failed_canonical_source_can_be_corrected_and_reacquired(tmp_path):
    inbox = tmp_path / "_inbox"
    src = tmp_path / "2401.12345.pdf"
    src.write_bytes(b"broken")
    first = A.acquire(src, inbox)
    P.provenance(inbox)
    assert A.load_log(inbox)[0]["status"] == "failed"

    src.write_bytes(b"%PDF-1.4\ncorrected\n%%EOF\n")
    second = A.acquire(src, inbox)
    assert second["status"] == "acquired" and second["urn"] == first["urn"]
    assert len(A.load_log(inbox)) == 1
    P.provenance(inbox)
    assert A.load_log(inbox)[0]["status"] == "registered"
    assert A.audit(inbox) == {"orphan_rows": [], "orphan_files": []}
