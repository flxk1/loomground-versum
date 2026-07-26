"""K2 snapshot minting and the K4 evidence facade, against a real synced store.

Each test tracks its falsifier from the K-plan:

  K2 — two stores with identical content mint identical versions; a touched
       (mtime-only) store minted the same; any content change mints a new one.
  K4 — a valid ref resolves to exactly the anchored span; a tampered source
       fails verify; batches are bounded and index-aligned.
"""
import json
from pathlib import Path

import pytest

import versum.profiles  # noqa: F401 — register built-in profiles
from versum import sync
from versum.identity.evidence import StoreEvidenceProvider
from versum.interop import EvidenceRef
from versum.ports import EvidenceProvider, MAX_EVIDENCE_BATCH
from versum.snapshot import require_graph_version

DOC = ("A breach is defined as an unauthorised disclosure of personal data. "
       "Negligence causes breaches. "
       "Notification means informing the authority without delay.")


def _config(tmp_path: Path, name="a", lib_id="lib-1", profile_id="generic",
            text=DOC, nd_systems=None) -> dict:
    kg_root = tmp_path / name / "kg"
    lib_root = tmp_path / name / "lib"
    lib_root.mkdir(parents=True, exist_ok=True)
    (lib_root / "policy" / "breach.txt").parent.mkdir(parents=True, exist_ok=True)
    (lib_root / "policy" / "breach.txt").write_text(text, encoding="utf-8")
    cfg_path = tmp_path / name / "config.json"
    cfg_path.write_text(json.dumps({
        "kg_root": str(kg_root),
        "profile_id": profile_id,
        "exclude_prefixes": ["_"],
        "nd_systems": nd_systems or [],
        "libraries": [{"id": lib_id, "root_path": str(lib_root),
                       "urn_namespace": "test", "registry_csv": None}],
    }), encoding="utf-8")
    return sync.load_config(cfg_path)


def _provider(cfg) -> StoreEvidenceProvider:
    return StoreEvidenceProvider.from_config(cfg)


def _claims(cfg) -> list:
    rows = []
    for table in sorted((Path(cfg["kg_root"]) / "by-domain").glob("*/claims.csv")):
        import csv
        with open(table, newline="", encoding="utf-8") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def _first_claim(cfg) -> dict:
    rows = _claims(cfg)
    assert rows, "sync produced no claims"
    return rows[0]


def _ref(cfg, provider, claim) -> EvidenceRef:
    return EvidenceRef(
        source_id=claim["canonical_urn"],
        item_id=claim["item_id"],
        span_start=int(claim["span_start"]),
        span_end=int(claim["span_end"]),
        content_digest=provider.content_digest(claim["canonical_urn"]),
        graph_version=require_graph_version(cfg["kg_root"]),
    )


# ── K2 ───────────────────────────────────────────────────────────
def test_equivalent_graphs_mint_identical_versions_across_arrangement(tmp_path):
    # Same content under a *different library id*: the ingest lane is storage
    # arrangement, not semantics, and must not enter the token.
    cfg_a = _config(tmp_path, "a", lib_id="lib-1")
    cfg_b = _config(tmp_path, "b", lib_id="lib-2")
    ra, rb = sync.sync_once(cfg_a), sync.sync_once(cfg_b)
    assert ra["graph_version"] == rb["graph_version"]
    assert ra["graph_version"].startswith("sha256:")


def test_only_semantic_change_mints_a_new_version(tmp_path):
    cfg = _config(tmp_path)
    v1 = sync.sync_once(cfg)["graph_version"]
    doc = Path(cfg["libraries"][0]["root_path"]) / "policy" / "breach.txt"

    # An mtime touch is not a semantic change.
    import os
    os.utime(doc, (1_800_000_000, 1_800_000_000))
    assert sync.sync_once(cfg)["graph_version"] == v1

    # Changing a claim-bearing sentence changes the materialized graph.
    doc.write_text(DOC.replace("Negligence causes", "Recklessness causes"),
                   encoding="utf-8")
    v2 = sync.sync_once(cfg)["graph_version"]
    assert v2 != v1


def test_profile_change_without_source_change_mints_a_new_version(tmp_path):
    # K2 falsifier (2026-07-21 review, finding 1): an extraction/profile change
    # with unchanged source bytes and unchanged claim count must re-materialize
    # the graph and mint a new version. The sentence carries exactly one marker
    # per profile — 'causes' (generic) vs 'announced' (news) — so the claim
    # count stays 1 while the stamped axes change.
    doc = "The ministry announced that stress causes errors."
    cfg = _config(tmp_path, text=doc, profile_id="generic")
    v1 = sync.sync_once(cfg)["graph_version"]
    before = _claims(cfg)
    assert [row["predicate"] for row in before] == ["causes"]

    cfg = _config(tmp_path, text=doc, profile_id="news")
    v2 = sync.sync_once(cfg)["graph_version"]
    after = _claims(cfg)
    assert [row["predicate"] for row in after] == ["announced"]
    assert len(after) == len(before)
    assert v2 != v1


def test_nd_only_configuration_change_mints_a_new_version(tmp_path):
    # K2 falsifier (2026-07-21 review, finding 1): an nD-only configuration
    # change must mint a new version — the nD-system manifest is a semantic
    # input to the materialized graph even when no source byte changed.
    cfg = _config(tmp_path)
    v1 = sync.sync_once(cfg)["graph_version"]

    nd_path = tmp_path / "a" / "math.json"
    nd_path.write_text(json.dumps({
        "id": "math", "namespace": "other.math", "version": "1",
        "axes": {"variable_space": {"value_type": "string"}},
    }), encoding="utf-8")
    cfg = _config(tmp_path, nd_systems=[str(nd_path)])
    report = sync.sync_once(cfg)
    assert report["indexed"] == 0  # no source was re-extracted
    assert report["graph_version"] != v1


# ── K4 ───────────────────────────────────────────────────────────
def test_valid_ref_resolves_to_exactly_the_anchored_span(tmp_path):
    cfg = _config(tmp_path)
    sync.sync_once(cfg)
    provider = _provider(cfg)
    claim = _first_claim(cfg)
    ref = _ref(cfg, provider, claim)

    assert isinstance(provider, EvidenceProvider)
    assert provider.verify(ref) is True
    content = provider.resolve(ref)["content"]
    anchored = content[ref.span_start:ref.span_end].strip()
    assert anchored == claim["text"].strip()


def test_missing_or_malformed_digest_fails_verify(tmp_path):
    # The digest is mandatory: a ref that omits or mangles it cannot verify,
    # even when source, item, and span are all good.
    import dataclasses
    cfg = _config(tmp_path)
    sync.sync_once(cfg)
    provider = _provider(cfg)
    good = _ref(cfg, provider, _first_claim(cfg))

    assert provider.verify(good) is True
    assert provider.verify(dataclasses.replace(good, content_digest="")) is False
    assert provider.verify(dataclasses.replace(good, content_digest="sha256:abc")) is False
    assert provider.verify(
        dataclasses.replace(good, content_digest="sha1:" + "0" * 40)) is False


def test_tampered_source_and_ghost_refs_fail_verify(tmp_path):
    cfg = _config(tmp_path)
    sync.sync_once(cfg)
    provider = _provider(cfg)
    claim = _first_claim(cfg)
    ref = _ref(cfg, provider, claim)
    v = provider.graph_version

    assert provider.verify(ref) is True
    doc = Path(cfg["libraries"][0]["root_path"]) / "policy" / "breach.txt"
    doc.write_text(DOC.replace("unauthorised", "sanctioned"), encoding="utf-8")
    # The SAME provider instance must see the tamper (no content cache).
    assert provider.verify(ref) is False

    assert provider.verify(EvidenceRef(source_id="urn:test:ghost",
                                       graph_version=v)) is False
    assert provider.verify(EvidenceRef(source_id=claim["canonical_urn"],
                                       item_id="item-nonexistent",
                                       graph_version=v)) is False
    with pytest.raises(KeyError):
        provider.resolve(EvidenceRef(source_id="urn:test:ghost", graph_version=v))


def test_snapshot_binding_rejects_empty_arbitrary_and_stale_tokens(tmp_path):
    # The provider binds to one minted graph_version at construction; a ref
    # carrying any other token — empty, invented, or from a prior snapshot —
    # is rejected outright.
    import dataclasses
    cfg = _config(tmp_path)
    sync.sync_once(cfg)
    provider = _provider(cfg)
    good = _ref(cfg, provider, _first_claim(cfg))
    assert provider.verify(good) is True

    for token in ("", "g1", "sha256:" + "0" * 64):
        bad = dataclasses.replace(good, graph_version=token)
        assert provider.verify(bad) is False
        with pytest.raises(ValueError, match="snapshot"):
            provider.resolve(bad)

    # After the store moves on, the old provider's snapshot is stale by
    # construction: a new provider carries the new token and rejects old refs.
    doc = Path(cfg["libraries"][0]["root_path"]) / "policy" / "breach.txt"
    doc.write_text(DOC.replace("Negligence causes", "Recklessness causes"),
                   encoding="utf-8")
    sync.sync_once(cfg)
    fresh = _provider(cfg)
    assert fresh.graph_version != provider.graph_version
    assert fresh.verify(good) is False


def test_provider_construction_fails_on_a_never_synced_store(tmp_path):
    cfg = _config(tmp_path)  # store created but never synced: nothing stamped
    with pytest.raises(ValueError, match="graph_version"):
        _provider(cfg)


def test_batches_are_bounded_and_index_aligned(tmp_path):
    cfg = _config(tmp_path)
    sync.sync_once(cfg)
    provider = _provider(cfg)
    claim = _first_claim(cfg)
    good = _ref(cfg, provider, claim)
    ghost = EvidenceRef(source_id="urn:test:ghost",
                        graph_version=provider.graph_version)

    assert provider.verify_batch([good, ghost, good]) == [True, False, True]
    resolved = provider.resolve_batch([ghost, good])
    assert resolved[0] is None
    assert resolved[1]["source_id"] == claim["canonical_urn"]

    with pytest.raises(ValueError, match="exceeds"):
        provider.verify_batch([good] * (MAX_EVIDENCE_BATCH + 1))


def test_oversize_batches_are_rejected_without_materialization(tmp_path):
    # The bound is enforced while consuming: a non-terminating iterable is
    # refused at the first excess item instead of hanging or exhausting memory.
    import itertools
    cfg = _config(tmp_path)
    sync.sync_once(cfg)
    provider = _provider(cfg)
    good = _ref(cfg, provider, _first_claim(cfg))

    endless = (good for _ in itertools.count())
    with pytest.raises(ValueError, match="exceeds"):
        provider.verify_batch(endless)


def test_solver_evidence_check_passes_end_to_end(tmp_path):
    """The K4 falsifier's integration leg: the Solver's own handler, wired to
    the live-store provider, accepts a candidate minted from a synced claim."""
    repo_parent = Path(__file__).resolve().parents[2]
    solver_root = next((repo_parent / name for name in ("loomground-solver", "solver")
                        if (repo_parent / name / "loomground_solver").exists()), None)
    language_src = next(
        (repo_parent / name / "src" for name in ("loomground-governance", "language")
         if (repo_parent / name / "src" / "loomground_governance").exists()), None)
    if solver_root is None:
        pytest.skip("solver repo not available")
    if language_src is None:
        pytest.skip("language repo not available")
    # Both roots must be inserted for a standalone run: the solver imports
    # loomground_governance, and a stale site-packages namespace shadows it
    # unless the language source precedes it on sys.path.
    import sys
    added = [str(solver_root), str(language_src)]
    sys.path[:0] = added
    try:
        from loomground_solver.handler import UniversalHandler
        from loomground_solver.adapters.versum import ClaimAxesDecoder
        from loomground_solver import interop as solver_interop
    finally:
        for entry in added:
            sys.path.remove(entry)

    cfg = _config(tmp_path)
    report = sync.sync_once(cfg)
    provider = _provider(cfg)
    claim = _first_claim(cfg)

    from versum.reasoning import request_from_claims
    row = dict(claim)
    row["sha256"] = provider.content_digest(claim["canonical_urn"])
    req = request_from_claims("req-e2e", {"question": "grounded?"}, [row],
                              graph_version=report["graph_version"])
    # Same wire, solver-side types; the claim text must match its anchored span
    # for the grounding check, which the extractor guarantees for short sentences.
    solver_req = solver_interop.ReasoningRequest.from_dict(req.to_dict())
    handler = UniversalHandler(evidence_provider=provider,
                               compilers=[ClaimAxesDecoder()])
    result = handler(solver_req)
    assert result.status == "complete"
    assert result.accepted == (claim["item_id"],)


def test_pdf_sources_fail_closed(tmp_path):
    cfg = _config(tmp_path)
    sync.sync_once(cfg)
    provider = _provider(cfg)
    # Rewrite the source index to point at a PDF: resolution must refuse, not guess.
    provider._sources = {"urn:test:pdf": {"library": "lib-1", "path": "x.pdf"}}
    ref = EvidenceRef(source_id="urn:test:pdf",
                      graph_version=provider.graph_version)
    assert provider.verify(ref) is False
    with pytest.raises(ValueError, match="PDF"):
        provider.resolve(ref)
