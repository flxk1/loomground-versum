"""Optional corpus regression — measure the pipeline on ANY corpus + gold set.

Domain-agnostic and ships NO domain data. Point it at a corpus and a gold file via
environment variables; it skips unless both are set:

    VERSUM_CORPUS       a folder of documents to index
    VERSUM_GOLD         a gold file (one concept slug per line)
    VERSUM_PROFILE      profile id (default 'generic')
    VERSUM_RECALL_FLOOR minimum gold recall to pass (default 0.5)

The corpus and gold set are the user's data for their domain; the engine holds neither.
"""
import csv
import os
from pathlib import Path

import pytest

from versum.store.index import index_folder
from versum.concept import curate
from versum.eval import score, load_gold
import versum.profiles  # noqa: F401 — register built-ins


def test_corpus_regression(tmp_path):
    corpus = os.environ.get("VERSUM_CORPUS")
    gold = os.environ.get("VERSUM_GOLD")
    if not (corpus and gold and Path(corpus).exists() and Path(gold).exists()):
        pytest.skip("set VERSUM_CORPUS and VERSUM_GOLD to run the corpus regression")

    profile = os.environ.get("VERSUM_PROFILE", "generic")
    floor = float(os.environ.get("VERSUM_RECALL_FLOOR", "0.5"))

    index_folder(corpus, profile)
    curate.suggest_folder(corpus)
    q = Path(corpus) / ".versum" / "curation" / "suggested_concepts.csv"
    with open(q, newline="", encoding="utf-8") as fh:
        found = {r["concept_id"] for r in csv.DictReader(fh)}

    r = score(found, load_gold(gold))
    assert r["recall"] >= floor, (
        f"gold recall {r['recall']:.2f} < floor {floor} "
        f"(precision {r['precision']:.2f}, tp {r['tp']}, fn {r['fn']})")
