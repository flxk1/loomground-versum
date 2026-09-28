# nD assignments on the index

`versum index <folder> --profile <profile>` writes `nD` (n-dimension, plane-native)
coordinate assignments — not just the 5D position on `entries.csv` — for every plane
installed and discovered through the `loomground.planes` entry-point group. This
document is the ground truth for what lands in `<store>/nd/assignments.csv`, which
systems/axes contribute, and how the columns relate to the framework's 5D manifold.

See also `docs/architecture/planes.md` (decision D1 / "Round 4" / "Round 5") for the
underlying design; this document is the index-output-facing summary.

## Files written under `<store>/nd/`

| file | what |
|---|---|
| `systems.json` | the run's `NDRegistry` manifest: every registered nD system (core + each discovered plane's own), keyed by system id, with its version |
| `assignments.csv` | one row per coordinate value a plane (or the core context) assigned to a subject (an entry, or a source URN for jurisdiction/time) |
| `bindings.csv` | one row per form-slot binding a plane's claim declared, pointing at the `assignment_id` it binds |

## `assignments.csv` columns

```
assignment_id, subject_id, system_id, system_version, axis_id, value, source_id, method,
confidence, verification
```

- `subject_id` — the entry's `item_id` (`ent-...`) for plane coordinates, or the
  source's URN for the core `jurisdiction`/`time` coordinates.
- `system_id` / `system_version` — the nD system that owns `axis_id` (e.g.
  `loomground-deontic` / `0.2.1`, `loomground-factual` / `0.1.0`, `versum-context` / `1`
  for the framework's own core system).
- `value` — JSON-encoded (a bare string is stored quoted, e.g. `"lender"`); read it back
  through `versum.nd.load_assignments`, which returns the parsed value, not the raw cell.
- `method` / `verification` — provenance: which producer/derivation wrote the row, and
  its verification state (always `"candidate"` for a fresh index run; curation is a
  separate, later step).

`bindings.csv` adds `binding_id, claim_id, form_slot, semantic_role, assignment_id,
axis_id, value, source_id, method, confidence, verification` — every row's
`assignment_id` names the `assignments.csv` row it binds to a claim's form slot.

**Backward compatibility**: this column set/order, and the signatures of
`versum.nd.load_assignments(path)` and `versum.store.graph.load_claims(path)`, are a
consumer seam — `ctrl-legal/router/adapters/grounding.py` reads a versum store through
exactly these two functions and these column names. New columns may only be added,
never renamed or removed, without breaking that consumer.

## Which systems/axes are written, and when

| system | axis(es) | written when |
|---|---|---|
| `versum-context` (core) | `jurisdiction`, `time` | a `consume` registry row or a KG sidecar supplies provenance for the source (never inferred/fabricated) — subject is the **source URN**, applies to every entry of that source |
| `loomground-deontic` | `operator`, `bearer`, `action`, `condition`, `negated` | the deontic plane's surface markers match a sentence (a modal marker: "must", "must not", "may", "shall", ...) |
| `loomground-factual` | `subject`, `predicate`, `object`, `polarity`, `quantification` | (a) the factual plane's own markers match a sentence directly, or (b) a norm's `spans.content` is lowered through the factual plane (see "A norm's content" below) |
| `loomground-epistemic` | plane-defined (`operator`, `holder`, `certainty`, ...) | the epistemic plane's own markers match (e.g. "knows that", "believes that") |
| `loomground-topos` | `rank`, `level`, `organ`, `competence`, `scope`, `reception` | **only** when the source's own metadata (a KG sidecar / consume-registry provenance passed as `context["source"]`) states it — never inferred from prose |
| `loomground-governance` | plane-defined (`node_class`, `token_kind`, `verdict`, ...) | the governance plane's own gate-detection markers match |

A plane that finds nothing on a sentence simply contributes zero rows for it; there is
no placeholder/empty row.

## 5D is what IS; O/P/F are OUGHT and carry no 5D dimension

The deontic plane's `binding()` is contractually always `{}` — an operator (`O`
obligation / `P` permission / `F` prohibition) is a normative force, not a fact on the
5D manifold. `versum.planes.build_source_entries` fails closed (raises
`PlaneIndexError`) if the plane registered as `"deontic"` ever publishes a non-empty
binding. Consequently:

- **No operator row, and no norm entry, ever carries a cross-profile 5D dimension under any
  name.** (There is no `dimension` column on `assignments.csv` in the first place; the
  invariant is enforced at the binding level, before any row is written.)
- A norm's **content** — the regulated action/state named by its `action` coordinate as
  literal text when the deontic plane first produces it — is lowered through the
  installed `factual` plane (with `context["subject"]` = the norm's bearer) and enters
  the 5D manifold as its **own action-type entry**: a factual claim carrying
  `"asserted": false` and `"entry_kind": "action_type"`. Its 5D dimension is whatever
  the factual plane's own binding gives a bare predication (`relational`, for the bare
  subject/predicate/object clauses this fixture exercises).
- That action-type entry is linked from the norm's own entry by an ordinary structural
  `"embeds"` link (`entry_links.csv`, `dimension: "structural"`), which is the *only*
  channel through which the norm's own entry gets any 5D contribution at all.
- The norm's own deontic `action` coordinate is re-pointed, after the fact, from the
  literal action text to a **reference**: the action-type entry's `item_id`. The claim
  as logged in `entry_claims.jsonl` is untouched (round-trip fidelity to `produce()`);
  only the derived `CoordinateAssignment`/`Binding` rows are re-pointed
  (`method: "versum-action-type-reference"`).

## Worked example: the `credit_policy_nd` fixture

`tests/fixtures/credit_policy_nd/policy.txt` (4 articles: a prohibition, a permission,
and two obligations) indexed with `--profile law-eu`, via `versum.store.index
.index_folder(folder, "law-eu", out, planes=versum.planes.DISCOVER)` — the exact call
`versum index` makes — writes, among others:

| article | operator | bearer | action-type asserted | action-type dimension |
|---|---|---|---|---|
| 1 ("must not make...") | `F` | `lender` | `false` | `relational` |
| 2 ("may use...") | `P` | `lender` | `false` | `relational` |
| 3 ("shall examine...") | `O` | `reviewer` | `false` | `relational` |
| 4 ("shall inform...") | `O` | `controller` | `false` | `relational` |

Article 1's negation follows the deontic plane's own convention: "must not" lowers to
`operator: "F"` with `negated: false` — the prohibition is carried by the operator
itself, not by a separate negation flag on top of it.

`tests/test_nd_on_index.py` asserts every row of this table literally, plus that
`n_nd_assignments > 0`, that the `embeds` link exists from each norm to its action-type
entry, that each norm's `action` coordinate equals that entry's `item_id`, and that no
operator/norm row carries a 5D dimension. `tests/test_consumer_compat.py` exercises the
exact `load_assignments` / `load_claims` call shapes and column names
`grounding.py` uses.
