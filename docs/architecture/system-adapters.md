# Universal language and system adapters

Versum adapters translate external grammars, schemas, policy systems, and runtime
observations into one neutral Graph-Versum interchange model. Loomground is the reference
semantic adapter, but the protocol does not name or privilege it.

## Separation of meaning

An adapter preserves three layers:

1. the source system's local nodes, predicates, vocabularies, and version;
2. an explicit projection of every relation onto Federation-5D;
3. versioned nD systems, coordinate assignments, and claim-slot bindings.

A grammar describes syntax, not semantics. The generic structural fallback may project an
AST as nodes and structural containment edges, but it never guesses causal, intentional,
temporal, relational, or contextual meaning. Semantic projection requires an explicit,
versioned mapping supplied by an adapter.

## Universal contract

`versum.adapters.SystemAdapter` exposes system identity, capabilities, artifacts, nD
systems, parsing and validation hooks, semantic projection, canonical-observation import,
and export. Parsing and runtime evaluation remain optional: an adapter may consume a
canonical observation produced by any conforming implementation.

Every `GraphProjection` carries:

- adapter, system, grammar, mapping, and Federation-5D versions;
- typed system nodes;
- relations retaining the local predicate and universal 5D dimension;
- nD systems and provenance-bearing coordinate assignments;
- bindings from Versum claim-form slots to those assignments;
- warnings for deliberately unprojected or unexportable constructs.

Persisted projections use `nodes.json`, `relations.csv`, `assignments.csv`, `bindings.csv`,
`identity.json`, and `systems.json`. They are a self-contained Graph-Versum adapter layer.

## Loomground reference adapter

`versum.integrations.loomground.LoomgroundAdapter` consumes the authoritative language
card, EBNF, schemas, and vocabularies from `loomground-governance`. It generates a
policy-sensitive `loomground-governance` nD system and projects canonical Loomground
observations as follows:

| Loomground construct | Graph-Versum representation | Federation-5D |
|---|---|---|
| actor, human, gate, master | typed node plus `node_class` coordinate | structural |
| authority cord | `authority` system relation | intentional |
| pipe cord | `pipe` system relation | causal |
| egress cord | `egress` system relation | causal |
| `on_behalf_of` | delegation relation | relational |
| risk and autonomy grade | ordered nD coordinates | contextual |
| party | entity-reference coordinate | contextual |
| reservation and redress | constraint nodes, role relations, and coordinates | intentional |
| duration and on-elapse | nD temporal coordinates | contextual/temporal |

Risk and grade ladders are adapter policy inputs. Their default values come from the active
Loomground vocabulary, and their order is materialized as attested `precedes` relations.
Changing a ladder changes the generated nD-system version.

## Command line

Project a canonical observation produced by any conforming Loomground runtime:

```bash
versum adapt \
  --adapter loomground \
  --observation observation.json \
  --out .versum/adapters/loomground
```

The command does not evaluate policy and does not depend on a particular Loomground
runtime. Runtime-backed parsing is available through the Python adapter by supplying an
object conforming to Loomground's neutral implementation protocol.
