"""Coordinate-identity curation — the mental-model / concept layer.

Coordinates are content-derived: two claims from different sources sharing a signature +
key_term name the SAME concept (convergence), a concept_id owns its identity (bare slug,
never a urn), and the concept layer emerges deterministically with no model.
"""
import json

from versum.concept import canon
from versum.store.graph import CONCEPT_ID_RE


def _claim(item_id, urn, text, polarity="N", predicate="obligation",
           modality="req", quant="null", domain="dom-a", library="lib", marker="x"):
    return {"item_id": item_id, "canonical_urn": urn, "source_urn": urn, "text": text,
            "polarity": polarity, "predicate": predicate, "modality": modality,
            "quantification": quant, "domain": domain, "library": library, "marker": marker}


# ── key_term ──────────────────────────────────────────────────────────────────
def test_key_term_prefers_quoted():
    assert canon.key_term("A 'processor' is any body that does the thing.") == "processor"


def test_key_term_strips_leading_function_word_from_quote():
    assert canon.key_term('The term "the controller" applies here.') == "controller"


def test_key_term_falls_back_to_capitalized_phrase():
    kt = canon.key_term("The European Data Board coordinates the work.")
    assert kt == "european-data-board"


def test_key_term_falls_back_to_salient_token():
    kt = canon.key_term("this body handles and maintains supervision duties")
    assert kt == "supervision"          # longest non-function content token, deterministic


def test_key_term_tie_break_is_lexicographic():
    # 'coordinates' and 'supervision' are both 11 chars -> lexicographically smaller wins
    assert canon.key_term("it coordinates supervision") == "coordinates"


def test_key_term_empty_when_only_function_words():
    assert canon.key_term("") == "" and canon.key_term("the a of to") == ""


# ── coordinate identity ─────────────────────────────────────────────────────────
def test_coordinate_id_is_bare_slug_never_urn():
    coord = canon.coordinate_for(_claim("i1", "urn:x:1", "A 'processor' must act."))
    cid = canon.coordinate_id(coord)
    assert cid.startswith("m-") and CONCEPT_ID_RE.match(cid)
    assert not cid.startswith("urn")


def test_same_coordinate_across_sources_converges():
    # same signature + same key_term, two different sources -> ONE concept, two sources
    c1 = _claim("i1", "urn:x:1", "A 'processor' has a duty here.")
    c2 = _claim("i2", "urn:x:2", "Elsewhere the 'processor' has the same duty.")
    out = canon.build_canon([c1, c2])
    assert len(out["concepts"]) == 1
    (agg,) = out["concepts"].values()
    assert len(agg["sources"]) == 2 and len(agg["claims"]) == 2


def test_different_polarity_or_predicate_splits():
    c1 = _claim("i1", "urn:x:1", "A 'processor' duty.", polarity="N", predicate="obligation")
    c2 = _claim("i2", "urn:x:2", "A 'processor' fact.", polarity="D", predicate="statement")
    out = canon.build_canon([c1, c2])
    assert len(out["concepts"]) == 2


# ── convergence curve ───────────────────────────────────────────────────────────
def test_convergence_flattens_on_repeats():
    # source 1 mints; source 2 repeats the same coordinate -> mints nothing new
    c1 = _claim("i1", "urn:x:1", "A 'processor' duty.")
    c2 = _claim("i2", "urn:x:2", "A 'processor' duty again.")
    out = canon.build_canon([c1, c2])
    conv = out["convergence"]
    assert conv[0]["n_new"] == 1
    assert conv[1]["n_new"] == 0 and conv[1]["n_distinct"] == 1


def test_fingerprint_is_document_concept_set():
    c1 = _claim("i1", "urn:x:1", "A 'processor' duty.")
    c2 = _claim("i2", "urn:x:1", "A 'controller' duty.")   # same source, two coordinates
    out = canon.build_canon([c1, c2])
    assert len(out["fingerprints"]["urn:x:1"]) == 2


# ── materialized row projections ────────────────────────────────────────────────
def test_concept_and_edge_rows_are_canonical_keyed():
    c = _claim("i1", "urn:x:1", "A 'processor' duty.", library="digital-law")
    out = canon.build_canon([c])
    crows = canon.concept_rows(out)
    erows = canon.edge_rows(out)
    assert crows and crows[0]["canonical_urn"] == "urn:x:1"
    assert crows[0]["library"] == "digital-law"
    assert crows[0]["created_by"] == "curation:coordinate"
    assert erows and erows[0]["edge_type"] == "grounds"
    assert erows[0]["canonical_urn"] == "urn:x:1" and erows[0]["src_id"] == "i1"


# ── partial + merge (resumable / cross-domain convergence) ──────────────────────
def test_merge_partials_converges_cross_domain():
    # identical coordinate appears in TWO domains -> one global concept spanning both
    ca = _claim("i1", "urn:a:1", "A 'processor' duty.", domain="dom-a")
    cb = _claim("i2", "urn:b:1", "A 'processor' duty.", domain="dom-b")
    pa = canon.domain_partial(canon.build_canon([ca], domain_of=lambda c: "dom-a"), "dom-a")
    pb = canon.domain_partial(canon.build_canon([cb], domain_of=lambda c: "dom-b"), "dom-b")
    merged = canon.merge_partials([pa, pb])
    assert merged["n_concepts"] == 1
    (entry,) = merged["concepts"]
    assert entry["n_sources"] == 2 and entry["domains"] == ["dom-a", "dom-b"]
    assert merged["canon_by_domain"] == {"dom-a": 1, "dom-b": 1}


def test_salience_drops_oneoff_noise_but_keeps_cross_source_term():
    # 'the european board' (capitalized, unquoted) recurs across 2 sources -> canonical.
    # 'Kasper Rasmussen' (an author name) appears once, never quoted -> dropped; that claim
    # falls back to an axes-only coordinate (no guessed subject).
    c1 = _claim("i1", "urn:x:1", "The European Board coordinates the work.",
                polarity="D", predicate="holds")
    c2 = _claim("i2", "urn:x:2", "The European Board issues guidance.",
                polarity="D", predicate="holds")
    noise = _claim("i3", "urn:x:3", "As Kasper Rasmussen argues in the paper.",
                   polarity="D", predicate="holds")
    out = canon.build_canon([c1, c2, noise], min_df=2)
    ids = set(out["concepts"])
    assert "m-d-holds-european-board" in ids
    assert not any("rasmussen" in i for i in ids)   # one-off author name filtered out


def test_salience_off_keeps_raw_heuristic():
    noise = _claim("i3", "urn:x:3", "As Kasper Rasmussen argues here.", predicate="holds")
    out = canon.build_canon([noise], salience=False)
    assert any("rasmussen" in i for i in out["concepts"])   # raw heuristic keeps it


def test_partial_is_json_round_trippable():
    out = canon.build_canon([_claim("i1", "urn:x:1", "A 'processor' duty.")])
    part = canon.domain_partial(out, "dom-a")
    assert json.loads(json.dumps(part))["domain"] == "dom-a"


# ── folder + KG orchestration ───────────────────────────────────────────────────
def test_curate_domain_folder_writes_concept_tables(tmp_path):
    d = tmp_path / "dom-a"
    d.mkdir()
    import csv
    cols = ["canonical_urn", "library", "item_id", "source_urn", "text",
            "polarity", "predicate", "modality", "quantification"]
    rows = [
        {"canonical_urn": "urn:x:1", "library": "lib", "item_id": "i1",
         "source_urn": "urn:x:1", "text": "A 'processor' duty.", "polarity": "N",
         "predicate": "obligation", "modality": "req", "quantification": "null"},
        {"canonical_urn": "urn:x:2", "library": "lib", "item_id": "i2",
         "source_urn": "urn:x:2", "text": "The 'processor' duty recurs.", "polarity": "N",
         "predicate": "obligation", "modality": "req", "quantification": "null"},
    ]
    with open(d / "claims.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
    r = canon.curate_domain_folder(d)
    assert r["n_concepts"] == 1 and r["n_sources"] == 2
    assert (d / "concepts.csv").exists() and (d / "semantic_edges.csv").exists()
    assert (d / "canon.partial.json").exists()


def test_curate_kg_writes_canon_and_convergence(tmp_path):
    import csv
    bd = tmp_path / "by-domain"
    for dom, urn in (("dom-a", "urn:a:1"), ("dom-b", "urn:b:1")):
        d = bd / dom
        d.mkdir(parents=True)
        cols = ["canonical_urn", "library", "item_id", "source_urn", "text",
                "polarity", "predicate", "modality", "quantification"]
        with open(d / "claims.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
            w.writerow({"canonical_urn": urn, "library": "lib", "item_id": "i1",
                        "source_urn": urn, "text": "A 'processor' duty.", "polarity": "N",
                        "predicate": "obligation", "modality": "req",
                        "quantification": "null"})
    cfg = {"kg_root": str(tmp_path)}
    r = canon.curate_kg(cfg)
    assert r["n_domains"] == 2 and r["n_concepts"] == 1 and r["n_sources"] == 2
    canon_json = json.loads((tmp_path / "canon.json").read_text())
    assert canon_json["n_concepts"] == 1 and canon_json["identity_axes"]
    assert (tmp_path / "convergence.json").exists()
