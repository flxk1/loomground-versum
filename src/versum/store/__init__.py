"""The KG store: the graph model and how callers get things into and out of it.

`graph` is the three-level Source/Claim/Concept model; `kg` consumes an existing KG's
provenance; `retrieve` is hybrid matching (ADR-004) plus a dependency-free keyword-overlap
(Jaccard) search; `index` is the drop-in folder indexer and the engine's primary entry point;
`erasure` is logical delete + GDPR Art.17 purge (tombstoned through the event log, excluded
from every read); `distribution` is the asymmetric publish/unpublish layer (an ancestor's
published items flow DOWN, recorded through the same event log); `hierarchy` is the folder
ancestry + the aggregated read (own + descendants + ancestor-published) that `search_similar`
runs over.
"""
