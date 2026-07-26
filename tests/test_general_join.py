"""The GENERAL (no-sidecar) join — proven through the live pipeline.

The bug this guards against: capture wrote one URN into the registry while the indexer
keyed claims on a DIFFERENT URN (it slugged the full rel_path — extension and subdir and
all — instead of the file stem), so ``models_for_source(canonical)`` came back EMPTY for
any ordinary folder that carried no KG sidecar.

ADR-URN option A fixes it: ``write.resolve_identity`` and ``index._urn_for`` both call the
ONE shared ``identity.deterministic_identity``, so whichever rung settles identity, both
sides agree byte-for-byte. This test runs capture → index → curate on a plain
CELEX-numbered file with NO sidecar and asserts the URN is minted once, shared byte-for-byte,
extension-free, and joinable.

ADR-URN-2: with no scheme and no title, a real on-disk file resolves by CONTENT HASH, so the
URN is derived from the bytes, not the filename — but capture and index still agree because
they hash the same file.
"""
import csv
from pathlib import Path

from versum import write as w
from versum.store.index import index_folder
from versum.concept import curate
from versum.store import graph as g
import versum.profiles  # noqa: F401 — register built-ins


def _plain_folder(root: Path) -> None:
    # a plain CELEX-numbered file (the bare number, no "celex" prefix → the deterministic
    # identifier resolvers do NOT fire; the file is a real .txt on disk with no title, so
    # capture takes the shared CONTENT-HASH fallback) and crucially NO *.metadata.json
    # sidecar carrying a canonical_urn.
    (root / "32016R0679.txt").write_text(
        "'Controller' is defined as the body which determines the purposes. "
        "The controller shall ensure protection in every case.\n", encoding="utf-8")


def test_general_no_sidecar_join_through_pipeline(tmp_path):
    _plain_folder(tmp_path)

    # capture (writes the registry) then index (keys the claims)
    w.capture_folder(tmp_path, "law-eu")
    index_folder(tmp_path, "law-eu")

    # the URN capture recorded in the registry
    reg = w.load_registry(tmp_path)
    assert len(reg) == 1
    registry_urn = reg[0]["urn"]
    assert reg[0]["identity_method"] == "content-sha256"   # the content rung, not a scheme

    # no KG sidecar was present → the URN is minted, not reused
    srcs = list(csv.DictReader(
        open(tmp_path / ".versum" / "sources.csv", newline="", encoding="utf-8")))
    assert srcs and all(s["provenance"] == "minted" for s in srcs)   # (b)
    assert all(s["provenance"] != "kg-canonical" for s in srcs)

    # (a) registry URN and EVERY claim's source_urn are byte-identical
    claims = g.load_claims(tmp_path / ".versum" / "claims.csv")
    assert claims, "the file produced no claims"
    assert all(c["source_urn"] == registry_urn for c in claims), \
        f"claim urns diverge from registry {registry_urn!r}: " \
        f"{sorted({c['source_urn'] for c in claims})}"
    assert all(s["source_urn"] == registry_urn for s in srcs)

    # (c) the URN is content-addressed — no file extension, no subdir slug, no filename at all
    assert registry_urn.startswith("urn:dls:sha256:")
    assert "txt" not in registry_urn
    assert "32016" not in registry_urn   # not filename-derived any more

    # (d) the join actually resolves: curate then traverse the live URN
    curate.suggest_folder(tmp_path)
    curate.confirm_folder(tmp_path, min_sources=1)
    claims = g.load_claims(tmp_path / ".versum" / "claims.csv")
    edges = g.load_edges(tmp_path / ".versum" / "semantic_edges.csv")
    models = g.models_for_source(registry_urn, claims, edges)
    assert len(models) > 0, \
        f"pipeline join failed: models_for_source({registry_urn!r}) is empty"


def test_canonical_identifier_join_through_pipeline(tmp_path):
    """The CANONICAL case — capture's identifier resolver FIRES (a CELEX-prefixed file).

    This is the real-corpus case and the one the path-slug-only fix missed: capture resolves
    ``urn:dls:celex:...`` while a slug-only indexer keyed ``urn:dls:source:celex-...`` — they
    diverged and ``models(canonical)`` was empty. Both sides now share the FULL identity
    resolution (identifier schemes + fallback), so the canonical URN joins.
    """
    # "CELEX_..." makes the law-eu CELEX resolver fire on the filename → a scheme URN.
    (tmp_path / "CELEX_32016R0679.txt").write_text(
        "'Controller' is defined as the body which determines the purposes. "
        "The controller shall ensure protection in every case.\n", encoding="utf-8")

    w.capture_folder(tmp_path, "law-eu")
    index_folder(tmp_path, "law-eu")

    reg = w.load_registry(tmp_path)
    registry_urn = reg[0]["urn"]
    # capture resolved the canonical CELEX scheme (NOT the path-slug fallback)
    assert registry_urn == "urn:dls:celex:32016r0679", registry_urn
    assert reg[0]["identity_method"] == "celex"

    srcs = list(csv.DictReader(
        open(tmp_path / ".versum" / "sources.csv", newline="", encoding="utf-8")))
    claims = g.load_claims(tmp_path / ".versum" / "claims.csv")
    assert claims
    # index keyed claims on the SAME canonical URN — the join that was broken
    assert all(s["source_urn"] == registry_urn for s in srcs), \
        f"index urns {[s['source_urn'] for s in srcs]} != registry {registry_urn!r}"
    assert all(c["source_urn"] == registry_urn for c in claims)

    curate.suggest_folder(tmp_path)
    curate.confirm_folder(tmp_path, min_sources=1)
    claims = g.load_claims(tmp_path / ".versum" / "claims.csv")
    edges = g.load_edges(tmp_path / ".versum" / "semantic_edges.csv")
    assert len(g.models_for_source(registry_urn, claims, edges)) > 0, \
        f"canonical join failed: models_for_source({registry_urn!r}) is empty"
