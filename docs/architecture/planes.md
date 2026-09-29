# Planes: entries, 5D positions and nD coordinates

Every sentence the versum indexes becomes an **entry**. Each entry has an exact span into
the source, a **five-value 5D position** (structural, causal, intentional, temporal,
relational) and exactly one **dominant dimension**. On top of that, every installed
Loomground **plane** (factual, epistemic, deontic, topos, governance) can write its own nD
coordinates onto the same entry. Code: `src/versum/planes.py` and
`src/versum/position5d.py`; wired into `versum index` in `src/versum/store/index.py`.

## The plane descriptor contract (v1)

A plane is a separate package that never imports the versum. It registers one entry point:

```toml
[project.entry-points."loomground.planes"]
<plane-id> = "<plane_package>.plane:plane"
```

`plane()` takes no arguments and returns a dict:

| key | meaning |
| --- | --- |
| `plane` | the plane id; must equal the entry-point name |
| `language_version` | the plane's own version, read from its package |
| `nd_system` | an nD-system document; `NDSystem.from_dict(d).validate()` must pass, its `version` must equal `language_version`, and `validation.unknown_values` must be `"reject"`. Planes omit the 5D version key; the versum supplies the default |
| `binding` | `{relation_or_field: dimension}`, loaded by the plane from one package data file; every value is one of the five dimensions; may be `{}` |
| `produce` | a pure, deterministic `produce(sentence, context=None) -> [claim]`; `[]` when the plane does not apply |
| `examples` | optional `[{"sentence", "expected": [claim]}]`: the plane's published examples |

A claim is `{"relation", "span": [start, end], "coordinates": {axis: value},
"slots": {form_slot: axis}, "links": [{"type", "relation", "to_span"}], "method"}`.
Spans are offsets into the sentence. `context` may carry `{"source": {...}}`: when a
registry backs the source, its provenance row; otherwise, when a folder-local KG sidecar
(`*.metadata.json`) matches the source, the **complete parsed sidecar** — every field it
carries, not only the identity fields `versum.store.kg.load_sidecars` keeps for its own
callers (`canonical_urn`, `title`, `jurisdiction`, ...) — so a plane's own metadata fields
(e.g. the topos plane's `rank`/`level`/`organ`/etc.) reach `produce()` even though
`load_sidecars` does not name them. Producers never repair an out-of-vocabulary value.

The versum reads a plane through the lean `PlaneAdapter` protocol (`plane_id`,
`language_version`, `nd_system()`, `binding()`, `produce()`), not the nine-method
`SystemAdapter`. `discover_planes()` loads the entry-point group; `discover_planes([...])`
and `index_folder(..., planes=[...])` take an explicit list of descriptors instead (the
injection seam used by the tests).

## What `versum index` does

`versum index <folder>` discovers the installed planes and needs no extra flag. (Called
from Python, `index_folder` uses no plane unless it gets `planes="discover"` or a list, so
a library call does not change with whatever happens to be installed.)

1. **Entries (A4).** Each source's text is split into sentences: paragraphs at blank
   lines; inside a paragraph, at `.`, `!`, `?` or `…` (plus closing quotes or brackets)
   followed by whitespace that does not lead into a lowercase letter, and at the CJK full
   stop, exclamation and question marks. A segment with no word character is not a
   sentence. Every sentence becomes an entry, whatever the profile's markers; the
   marker-gated `claims.csv` is unchanged. Spans index the unmodified source: the decoded
   file for text sources (CRLF kept), the extracted text layer for PDFs, and an entry's
   `text` is exactly that slice of it, for sentence and embedded entries alike.
2. **Embedded entries.** A claim whose span is not the whole sentence gets its own entry.
   Its parent is the smallest other entry of the sentence that encloses it, otherwise the
   sentence entry, and parent and child are joined by a `structural` link with relation
   `embeds`; that link also adds 1 to the **parent's** own structural 5D contribution (an
   entry that structurally contains another carries that much structural information
   itself — see "Defaults" below). A claim's own `links` become entry links of the stated
   dimension.
3. **A norm's content (the deontic bridge; ACTION-TYPE entries, Round 5).** No plane's
   `binding` puts an *ought* on the 5D manifold: an operator (O/P/F) is a normative force
   over a bearer:action pair, not a fact the 5D describes (decision **D1**; the deontic
   plane's own `binding()` is always `{}` — see `versum.deontic` and the deontic plane's
   own `nd_system()["describes"]` for the reasoning: *deontic is not causal — an ought is
   not an is*). This is a hard invariant, not just a convention this consumer follows: the
   generic per-claim 5D contribution code (`if relation in bind: c[bind[relation]] += 1`)
   fails closed — raises `PlaneIndexError`, refuses the run — if the plane registered as
   `"deontic"` were ever to publish a non-empty binding at all, rather than silently
   letting an operator start contributing to 5D under some new key.

   A norm's content still needs a 5D reading, so any claim (of any plane) that carries
   `spans.content = {"start", "end", "text"}` — the plane's own literal offset of its
   regulated content into the sentence, `sentence[start:end] == text` — plus a non-empty
   `bearer` coordinate has that content lowered through the installed `factual` plane, if
   one is installed, with `context["subject"]` set to the bearer. The result becomes its
   own **ACTION-TYPE entry** (a sub-span of the norm's sentence): the factual plane marks
   such a claim `asserted: false`, `entry_kind: "action_type"` (it never asserted the
   clause — its subject came from `context`, out of band, not from the sentence itself),
   under its own method label (`loomground-factual/content_clause`), and this consumer
   persists that claim exactly as produced (rule 4: the log in `entry_claims.jsonl`
   reproduces `produce()` field for field). The action-type entry is linked from the
   norm's own entry by the ordinary structural `embeds` link (same pattern as an
   epistemic attitude's link to its embedded proposition).

   The norm's own coordinate that named the content AS LITERAL TEXT (e.g. a deontic
   norm's `action` axis, `value_type: concept_reference`) is then **re-pointed**: the
   `CoordinateAssignment`/`Binding` rows the claim's own coordinate would otherwise have
   produced are replaced with a reference to the action-type entry's `item_id` — a
   concept reference, never the text a second time (see the deontic plane's own
   `nd_system()["describes"]`: *"the action axis ... is a reference (item_id / concept
   reference) to the action-type entry ..., never asserting the action into the norm's
   own coordinates"*). The coordinate to re-point is found generically — whichever of the
   claim's own coordinates has a value exactly equal to its `spans.content` text — so no
   axis name or plane id is hardcoded here. Negation is recorded once, on the norm (its
   `negated` axis is the sole authority for a not/never clause over the operator's
   proposition); the action-type entry's own `polarity` coordinate is kept too, for
   reference, but is never the ought-side authority on whether the norm is negated. The
   model stays open for a future, separately-asserted *observed-event* entry linked to
   the same action-type entry (an actual occurrence of the regulated action) — nothing
   beyond the link target exists for that yet.

   Concretely, for a deontic norm: its operator, bearer and condition stay nD coordinates
   *on the norm entry* exactly as before, but `action` now holds a reference, not text;
   its 5D position comes only from (a) whatever other plane also claims that sentence
   (e.g. governance's `decide`-gate reservation) and (b) the structural `embeds` link to
   its own action-type entry — never from the operator.

   **Abstention instead of a placeholder (`ACTION_IMPLICIT`).** A claim that names a
   bearer but publishes no usable `spans.content` — either no `spans.content` at all, or
   one whose own span invariant does not hold against the sentence
   (`sentence[start:end] != text`) — is never given a fabricated content/action-type
   entry. Instead `versum.planes.build_source_entries` records one abstention (reason
   code `versum.planes.ACTION_IMPLICIT`) into the store's append-only
   `.versum/abstentions.jsonl` (see "Files written" below) and moves on: no entry, no
   `embeds` link, no 5D contribution from the missing content. The invariant "every
   deontic action resolves through `embeds`" (`versum.planes.check_action_embeds_invariant`)
   applies only to claims that are **not** recorded there — an abstained norm is an
   explicit, re-checkable exception to it, never a silent gap.

   **Compatibility shim.** A reader still written against the pre-revert `claims.csv`
   `embeds`/`embedded_in` companion-row columns (see "The `law-eu` profile's normative
   predicates" below) should call `versum.planes.resolve_action_type(versum_dir,
   claim_entry_id)` instead of reaching into `claims.csv`: it follows the claim entry's
   outgoing `embeds` link in `entry_links.csv` and returns the target row from
   `entries.csv` (or `None` for an abstained/action-less claim). This is a TEMPORARY,
   single call site — its docstring and the module constant
   `versum.planes.RESOLVE_ACTION_TYPE_DELETION_DATE` (`2027-03-31`) name its deletion
   date; a test enforces the constant does not silently drift.
3. **Coordinates (A3).** Each claim coordinate becomes a `CoordinateAssignment` whose
   subject is the entry's `item_id`, with `system_id` and `system_version` from the
   plane's nD system (so a stale assignment is detectable), `source_id` from the source
   and `method` from the claim. Each slot becomes a `Binding` row
   (`claim_id = item_id`) checked against the system's binding rules. A list value on a
   many-valued, non-interval axis gives one assignment per element.
4. **Core coordinates.** Source-level `jurisdiction` and `time` keep their existing rows
   (subject = source URN) and apply to every entry of that source;
   `planes.entry_coordinates(entry, assignments)` returns both kinds.
5. **Fail closed (rule 6).** Every assignment and binding is validated against its
   plane's nD system inside the index run. An out-of-vocabulary value, an unknown axis, a
   slot without a binding rule or with a disallowed axis, a link or binding naming
   anything but the five dimensions, a bad span, a producer exception or an
   unserialisable claim raises `PlaneIndexError` (or `PlaneDescriptorError`) naming
   plane, axis and value. Nothing of the run is written, and a previous index stays as it
   was. The CLI exits with status 3 and prints the error as JSON on stderr.

## Defaults

| default | value |
| --- | --- |
| 5D position | contributions normalised to sum to 1 (six decimal places). Each claim adds 1 to the dimension its plane binds its `relation` to, and 1 for each coordinate field whose axis the plane binds; relations and fields the binding does not name add nothing. Each `embeds` link (parent-child containment, including a norm's link to its own content entry) adds 1 `structural` to the **parent's** contribution |
| dominant dimension | argmax of the contributions; ties go to the earliest of structural, causal, intentional, temporal, relational |
| no plane claims the sentence | position all zeros, `position_basis = default`, dominant `relational` |
| entry id | `ent-` + the first 16 hex digits of `sha1("<source_urn>|<start>|<end>")`: the same for every plane and every run |
| assignment / binding / link ids | `nda-` / `ndb-` / `enl-` + a 16-hex sha1 of their defining fields |
| plane order | sorted by plane id; a plane id registered twice fails closed |
| parent-child link | `structural`, relation `embeds`, method `versum-span-containment` |

## The `law-eu` profile's normative predicates (a separate, non-plane classification)

Independently of the plane pipeline above, `versum.profiles.law_eu` classifies each of
its own surface-marker-derived predicates to one of the five dimensions
(`versum.profile.Profile.predicate_dimensions`, `dimension_for`), for the
generic/scholarly extraction pipeline that never sees a plane's `spans` or a content
entry. The four **normative** predicates — "grants", "imposes", "permits", "prohibits"
(each an operator O/P/F or a Hohfeldian right/duty) — have **no entry in
`PREDICATE_DIMENSIONS` at all**, under any key spelling. This is Round 5's correction to
Round 4: Round 4 had already stopped reading the deontic plane's per-operator binding
(always `{}`) but still asserted the relational floor as a *static literal table entry*
for those three predicates ("imposes"/"permits"/"prohibits"); Round 5 removes even that —
a table entry, even one that names the relational floor, is still a predicate →
dimension MAPPING for a normative predicate, which is exactly what "no operator carries a
dimension under any name" rules out. `Profile.projections_5d()` (the audit
surface) reports every such predicate `dimension_5d: None`,
`verification: "not_declared"` — it never leaks `dimension_for`'s own framework-level
fallback back out as if the profile had declared a mapping.

**Round 6 briefly made `claims.csv` agree with that audit verdict by appending a
companion row** (`versum.io.extract.candidate_items` stamped the normative claim's own
`dimension` column empty and asserted the relational floor onto a second, linked
`type: "action"` row, `verification: "structural"`, in the same `claims.csv`, joined by
`embeds`/`embedded_in` columns). That row-doubling design is now **reverted (Round 7,
the Phase 0 ontology seam)**: it silently doubled the marker-gated claim count and put
norm content — never itself a curator-facing assertion — on the same write surface as
real candidate claims, one a naive `len(claims.csv rows)` consumer could not tell apart
from the other.

**Round 7 keeps only the part of Round 6 that is still true**: for a claim whose
predicate is in `Profile.unmapped_predicates()` (the normative operators, on any profile
that leaves any predicate unmapped — today only `law-eu`), the claim's own `dimension`
column is **empty** (`""`), never a fabricated floor value — matching
`projections_5d()`'s "not declared" exactly. It removes the companion row and the
`embeds`/`embedded_in` columns entirely: `claims.csv`'s header is exactly what it was
before Round 6, and `versum.store.graph.Claim` no longer declares those two fields. A
normative claim's action type is **never written to `claims.csv` at all**, under any
verification, dimension, or column name — it lives only where the plane pipeline already
puts a deontic norm's content: a not-asserted entry in the entry model (`entries.csv` /
`entry_claims.jsonl`), linked from the norm's own entry by the structural `embeds` link
(see the ACTION-TYPE entries section above), referenced by the owning plane's own action
nD coordinate. A norm with no extractable action span abstains (`ACTION_IMPLICIT`)
instead of manufacturing either kind of placeholder row.

This is enforced as a **write-boundary invariant**, not a reader flag:
`versum.store.graph.save_claims` raises `versum.store.graph.ClaimProvenanceError` for any
row lacking an asserted provenance chain — a recognised `verification`
(`versum.store.graph.ASSERTED_CLAIM_VERIFICATIONS`: `candidate` / `confirmed` /
`attested`) plus a `source_urn` and a span — before anything reaches disk. The reverted
companion row's own `verification="structural"` marker is exactly the shape this check
refuses, so the row-doubling design cannot silently return. `dimension_for` itself is
unchanged (`tests/test_profile_audit.py::test_dimension_for_is_unchanged_for_callers_that_need_a_concrete_value`):
it is still the one place a framework caller gets a concrete placeholder value; that value
is simply never asserted onto any `claims.csv` row again. See
`versum/profiles/law_eu.py`, `versum/io/extract.py::candidate_items`,
`versum/store/graph.py::Claim` / `save_claims` / `ClaimProvenanceError`, and
`versum/planes.py::ACTION_IMPLICIT` / `resolve_action_type` /
`check_action_embeds_invariant`.

A reader still written against the reverted `embeds`/`embedded_in` claims.csv columns has
exactly one migration path: `versum.planes.resolve_action_type` (see above), a temporary
shim with a stated deletion date.

The remaining, non-normative predicates ("holds", "conditions", "defines", "repeals",
"supersedes", "delegates") keep their existing table entries unchanged: none of them
carries an operator, so this classification does not touch them, and their claims.csv rows
carry their mapped dimension exactly as before (no action-type twin is created for them).

## Files written

| file | content |
| --- | --- |
| `.versum/entries.csv` | one row per entry: id, source, kind (`sentence` or `embedded`), parent, span, `text` (the exact source slice `source[span_start:span_end]`, not cleaned: CR and control characters are kept and the CSV quoting carries them), the five position values, dominant dimension, basis, planes, relations |
| `.versum/entry_links.csv` | links between entries, each with exactly one dimension |
| `.versum/entry_claims.jsonl` | every plane claim as produced, with its entry and plane version, so published examples can be read back field for field (rule 4) |
| `.versum/abstentions.jsonl` | append-only: one record per norm the pipeline declined to fabricate a content/action-type entry for, with a reason code (`versum.planes.ACTION_IMPLICIT`) — never a placeholder entry; see `versum.planes.check_action_embeds_invariant` |
| `.versum/nd/assignments.csv` | core source rows, followed by per-entry plane rows |
| `.versum/nd/bindings.csv` | per-entry plane bindings |
| `.versum/nd/systems.json` | the core system plus each plane's nD system |
