"""inbox/suggest — placement suggestions from shared concepts, on a synthetic store.

  S1  domain ranking     — a query sharing concepts with domain A ranks A above B.
  S2  nearest sources    — the closest source is the one with the most (rarity-weighted) overlap.
  S3  rarity matters     — a concept shared by every source carries less weight than a rare one.
  S4  no overlap         — a query sharing nothing returns empty, never a guessed domain.
"""
import csv
from pathlib import Path

from versum.ingestion import suggest as S


def _store(tmp_path, rows):
    """rows: {domain: {urn: [concept_ids]}} -> a by-domain/*/concepts.csv tree."""
    root = tmp_path / "by-domain"
    for dom, srcs in rows.items():
        d = root / dom
        d.mkdir(parents=True)
        with open(d / "concepts.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["canonical_urn", "library", "concept_id", "label", "domain"])
            for urn, cids in srcs.items():
                for c in cids:
                    w.writerow([urn, "lib", c, c, dom])
    return tmp_path


def test_s1_domain_ranking(tmp_path):
    _store(tmp_path, {
        "alpha": {"urn:a1": ["c-shared", "c-a1", "c-a2"], "urn:a2": ["c-a3", "c-a4"]},
        "beta":  {"urn:b1": ["c-b1", "c-b2"], "urn:b2": ["c-b3"]},
    })
    idx = S.build_index(tmp_path)
    r = S.rank_domains(["c-shared", "c-a1"], idx, top_k=5)
    assert r[0]["domain"] == "alpha"
    assert r[0]["nearest_source"] == "urn:a1"


def test_s2_nearest_sources(tmp_path):
    _store(tmp_path, {
        "alpha": {"urn:a1": ["c1", "c2", "c3"], "urn:a2": ["c1"]},
        "beta":  {"urn:b1": ["z1", "z2"]},
    })
    idx = S.build_index(tmp_path)
    r = S.nearest_sources(["c1", "c2", "c3"], idx, top_k=3)
    assert r[0]["urn"] == "urn:a1"                       # most overlap
    assert r[0]["score"] >= r[1]["score"]


def test_s3_rarity_weighting(tmp_path):
    # c-common is in every source (idf 0); c-rare in one. Sharing the rare one must win.
    _store(tmp_path, {
        "alpha": {"urn:a1": ["c-common", "c-rare"]},
        "beta":  {"urn:b1": ["c-common"], "urn:b2": ["c-common"], "urn:b3": ["c-common"]},
    })
    idx = S.build_index(tmp_path)
    assert idx.idf["c-rare"] > idx.idf["c-common"]
    r = S.rank_domains(["c-rare", "c-common"], idx, top_k=5)
    assert r[0]["domain"] == "alpha"


def test_s4_no_overlap_no_guess(tmp_path):
    _store(tmp_path, {"alpha": {"urn:a1": ["c1", "c2"]}})
    idx = S.build_index(tmp_path)
    out = S.suggest(["totally-unrelated"], idx)
    assert out["domains"] == [] and out["sources"] == []   # nothing shared → no suggestion


# ── S5 — cascade routes by evidence shape (regex → local → cloud) ──
def test_s5_tier_regex_when_dominant():
    ranked = [{"domain": "a", "score": 0.30}, {"domain": "b", "score": 0.05}]
    assert S.recommend_tier(ranked)["tier"] == "regex"


def test_s5_tier_local_when_close():
    ranked = [{"domain": "a", "score": 0.20}, {"domain": "b", "score": 0.18}]
    assert S.recommend_tier(ranked)["tier"] == "local-llm"


def test_s5_novel_capped_to_local_by_default():
    # cascade wants cloud for a novel item, but the default policy is cloud-opt-in → capped local.
    assert S.recommend_tier([])["tier"] == "local-llm"
    assert S.recommend_tier([], S.Policy(allow_cloud=True))["tier"] == "cloud-llm"
    assert S.recommend_tier([], S.Policy(local_available=False))["tier"] == "review"


# ── S6 — explicit policy modes override the cascade ──
def test_s6_mode_cloud_everything():
    ranked = [{"domain": "a", "score": 0.30}, {"domain": "b", "score": 0.05}]   # would be regex
    assert S.recommend_tier(ranked, S.Policy(mode="cloud"))["tier"] == "cloud-llm"


def test_s6_mode_local_and_deterministic():
    ranked = [{"domain": "a", "score": 0.30}, {"domain": "b", "score": 0.05}]
    assert S.recommend_tier(ranked, S.Policy(mode="local"))["tier"] == "local-llm"
    assert S.recommend_tier(ranked, S.Policy(mode="deterministic"))["tier"] == "regex"


def test_s6_load_policy_from_dict():
    p = S.load_policy({"effort": {"mode": "cloud", "allow_cloud": True}})
    assert p.mode == "cloud" and p.allow_cloud is True
    assert S.load_policy(None).mode == "cascade"           # default when absent


def test_s6_load_policy_from_file(tmp_path):
    import json as _j
    f = tmp_path / "eff.json"
    f.write_text(_j.dumps({"effort": {"mode": "local", "local_available": True}}))
    p = S.load_policy(str(f))
    assert p.mode == "local"
    assert S.load_policy(str(tmp_path / "missing.json")).mode == "cascade"   # absent → default
