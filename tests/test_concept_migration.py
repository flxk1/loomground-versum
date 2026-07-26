import json

import pytest

from versum.store.graph import Concept, deprecate_concepts


def test_concept_deprecation_preserves_old_row_and_adds_aliases():
    concepts = [Concept("processors", "Processors").row(),
                Concept("processor", "Processor").row()]
    out = deprecate_concepts(concepts, {"processors": "processor"})
    by_id = {c["concept_id"]: c for c in out}
    assert by_id["processors"]["status"] == "deprecated"
    assert by_id["processors"]["superseded_by"] == "processor"
    assert set(json.loads(by_id["processor"]["aliases"])) == {"Processors", "processors"}


def test_concept_deprecation_rejects_missing_or_self_target():
    concepts = [Concept("a", "A").row()]
    with pytest.raises(KeyError):
        deprecate_concepts(concepts, {"a": "b"})
    with pytest.raises(ValueError):
        deprecate_concepts(concepts, {"a": "a"})
