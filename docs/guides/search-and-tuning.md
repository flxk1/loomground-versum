# Runbook — search the KG + the new tuning dials

After re-extraction + curation, four new capabilities are available. All are config-driven and
device-neutral.

## 1. Morphology (collapse inflected variants) — `morph_language`

Inflected forms of one term (`produkts` / `produkt` / `produkten`) otherwise mint separate
concepts. Add to the config:

```json
"morph_language": "auto"
```

- `"auto"` (recommended) — dependency-free, precise: strips only inflectional endings
  (`es/en/e/s`); keeps `provider`≠`provide`, converges `produkt*` and plurals.
- `"german"` / `"english"` / … — the Snowball stemmer: higher recall but **aggressive** (may
  merge distinct lexemes like `Wette`/`Wetter`). Opt-in only.
- omit / `null` — off (current behaviour).

The concept id uses the normalized form; the **label keeps the most frequent surface form**, so
readability is preserved. Re-run `curate_full.py --force` after changing it.

## 2. Per-domain profiles (right axes per field) — `domain_profiles` + `scholarly`

The axis half of a coordinate (`predicate`/`modality`) is profile-stamped. Non-law domains
under `law-eu` get legal predicates they don't have. Route them to the new `scholarly` profile
(neutral academic predicates: defines/asserts/relates/causes/enables/prevents/supports/refutes):

```json
"profile_id": "law-eu",
"domain_profiles": {
  "classic_philosophy": "scholarly",
  "philosophy_of_mind_and_cognitive_science": "scholarly",
  "computer_science_and_cybernetics": "scholarly",
  "economics_and_political_economy": "scholarly",
  "economics_and_data_markets": "scholarly",
  "information_economics_and_knowledge": "scholarly"
}
```

`reextract_full.py` reads this and extracts each listed domain with its profile. Re-extract
those domains (or `--force` all), then re-curate. On philosophy prose `scholarly` extracts ~6×
the typed claims `law-eu` does, with no legal-predicate leakage.

## 3. Higher-order models — `--m-max 2`

`curate_full.py --config … --m-max 2` additionally mints **depth-2 composite concepts**:
coordinate PAIRS that co-occur within a source's unit and recur across ≥ 2 sources (a "these two
propositions travel together" model). Composite ids start `m2-`; they're grounded by the
co-occurring claims and appear in `canon.json` with `"m": 2` and their `constituents`. M=1 is
unchanged; deeper tuples are a future extension. Start at M=1, move to `--m-max 2` once the
clean corpus makes M=1 solid.

## 4. Search the KG — `versum search`

Deterministic facet + BM25 retrieval over claims and concepts:

```bash
cd loomground-curation/loomground-versum
python3 -m versum search --config "<kg cfg>" --q "controllers and processors" \
        --filter type=concept --filter predicate=imposes -k 10
```

Facets (repeatable `--filter field=value`): `type` (claim|concept|composite), `polarity`,
`predicate`, `modality`, `quantification`, `domain`, `library`, `concept_id`, `m`. Omit `--q`
for pure facet browsing; combine `--q` + filters for scoped keyword search.

### Optional: local-model semantic rerank

The dense layer is an injected, device-side adapter (your Ollama Qwen/Phi) — the engine never
calls a model itself. To turn on semantic rerank in your own script:

```python
from versum.retrieve import from_kg
from versum.integrations.ollama import OllamaDense
idx = from_kg(kg_root, dense=OllamaDense(model="qwen2.5:0.5b"))
idx.search("obligations on data processors", filters={"type": "concept"}, k=10)
```

Needs Ollama running locally with an embedding model pulled; it falls back to facet+BM25 if the
model is unreachable, so search always works.
