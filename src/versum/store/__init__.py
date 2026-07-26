"""The KG store: the graph model and how callers get things into and out of it.

`graph` is the three-level Source/Claim/Concept model; `kg` consumes an existing KG's
provenance; `retrieve` is hybrid matching (ADR-004); `index` is the drop-in folder
indexer and the engine's primary entry point.
"""
