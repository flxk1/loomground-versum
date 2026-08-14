"""versum/store/hierarchy.py — the asymmetric folder hierarchy + distribution read.

The store is per-workspace: each folder carries its own KG store in a ``.versum``
sub-directory. The folder tree defines an **asymmetric** read scope:

  * Memory flows **UP** — a folder's view always includes its **own** store plus every
    **descendant** folder's store. A parent sees everything beneath it.
  * Memory does **not** flow down or sideways — a folder never reads a sibling's store, and
    reads an ancestor's store **only** for the items that ancestor has explicitly
    :func:`published <versum.store.distribution.publish>`.

The asymmetry is structural, enforced here by :func:`discover_descendants` /
:func:`discover_ancestors` (which never open a sibling), not by policy: a folder at
``…/acme/Engineering/`` simply never looks at ``…/acme/HR/``.

:func:`aggregate_docs` folds those three scopes into one :class:`~versum.store.retrieve.Doc`
set — own + descendants (full) + ancestor-published (filtered) — honouring erasure at every
layer (a tombstoned item is dropped before the publish filter, so an erased node is never
distributed). :func:`from_folder` wraps that set in a
:class:`~versum.store.retrieve.SearchIndex`, so ``from_folder(folder).search_similar(query)``
searches the whole aggregated scope.

Ported from host's ``WorkspaceMemory`` folder-discovery + aggregation semantics
(``discover_folders`` / ``discover_ancestors`` / ``discover_descendants`` / ``search`` /
``all_pairs``) so host can retire the last of its parallel store.
"""
from __future__ import annotations

from pathlib import Path

from .distribution import load_distribution
from .retrieve import (
    Dense,
    SearchIndex,
    docs_from_dimensioned_store,
    docs_from_kg,
)

#: The per-folder store directory. Each workspace folder that participates in the graph
#: carries one; its contents are a normal ``kg_root`` (``by-domain/``, ``_events.jsonl``, …).
VERSUM_DIRNAME = ".versum"


def kg_root_for(folder) -> Path:
    """The ``kg_root`` (``.versum`` store dir) for a workspace ``folder``."""
    return Path(folder).expanduser() / VERSUM_DIRNAME


def has_store(folder) -> bool:
    """True when ``folder`` carries a ``.versum`` store."""
    return kg_root_for(folder).is_dir()


def discover_descendants(folder) -> list[Path]:
    """Every folder that is ``folder`` **or a descendant** and carries a ``.versum`` store.

    The UP-flow scope. Sibling folders are excluded by construction — the walk is rooted at
    ``folder``. ``folder`` itself is included when it has a store. Returned sorted for a
    deterministic scope order.
    """
    folder = Path(folder).expanduser().resolve()
    found: set[Path] = set()
    if (folder / VERSUM_DIRNAME).is_dir():
        found.add(folder)
    if folder.is_dir():
        for store in folder.rglob(VERSUM_DIRNAME):
            if store.is_dir():
                found.add(store.parent.resolve())
    return sorted(found)


def discover_ancestors(folder) -> list[Path]:
    """Every **strict** ancestor of ``folder`` that carries a ``.versum`` store.

    Shallowest first (closest to the workspace root). ``folder`` itself is excluded. These
    are the folders whose :func:`published <versum.store.distribution.publish>` items flow
    DOWN to ``folder``; their private items are never visible here.
    """
    folder = Path(folder).expanduser().resolve()
    ancestors: list[Path] = []
    for parent in folder.parents:
        if (parent / VERSUM_DIRNAME).is_dir():
            ancestors.append(parent)
    ancestors.reverse()  # Path.parents is nearest-first; return shallowest-first
    return ancestors


def _scope_order(folder: Path, descendants: list[Path]) -> list[Path]:
    """``folder`` first (own store wins conflicts), then descendants by path."""
    return sorted(descendants, key=lambda d: (d != folder, str(d)))


def _aggregate(folder, docs_loader, *, exclude_erased: bool = True, **kw) -> list:
    """Fold the three folder scopes into one deduplicated Doc set via a pluggable loader.

    ``docs_loader(kg_root, *, exclude_erased, **kw) -> list[Doc]`` selects the persistence
    representation — :func:`~versum.store.retrieve.docs_from_kg` for the claims/overlay store,
    :func:`~versum.store.retrieve.docs_from_dimensioned_store` for the dimensioned-subgraph
    sink store. The asymmetric hierarchy semantics (own + descendants full, ancestor-published
    filtered, erasure honoured at every layer before the publish filter) are identical for both
    because they turn only on ``Doc.doc_id`` / ``Doc.canonical_urn``, which both loaders carry.
    """
    folder = Path(folder).expanduser().resolve()
    by_id: dict[str, object] = {}

    # 1 + 2: own + descendants — every live doc (memory flows UP).
    for scope in _scope_order(folder, discover_descendants(folder)):
        for doc in docs_loader(kg_root_for(scope), exclude_erased=exclude_erased, **kw):
            by_id.setdefault(doc.doc_id, doc)

    # 3: ancestors — only the docs that ancestor published flow DOWN.
    for ancestor in discover_ancestors(folder):
        anc_root = kg_root_for(ancestor)
        dist = load_distribution(anc_root)
        if not (dist.published_nodes or dist.published_sources):
            continue
        for doc in docs_loader(anc_root, exclude_erased=exclude_erased, **kw):
            if doc.doc_id in by_id:
                continue
            if dist.distributes(doc.doc_id, doc.canonical_urn):
                by_id[doc.doc_id] = doc

    return sorted(by_id.values(), key=lambda d: d.doc_id)


def aggregate_docs(folder, *, exclude_erased: bool = True, **kw) -> list:
    """The aggregated claims/overlay-store :class:`~versum.store.retrieve.Doc` set visible from
    ``folder``.

    Union of three scopes, deduplicated by ``doc_id`` (own store wins on conflict):

      1. ``folder``'s own store — every live doc.
      2. every descendant store — every live doc (memory flows UP).
      3. every ancestor store — only docs that ancestor has **published**
         (:class:`~versum.store.distribution.Distribution`), the sole items that flow DOWN.

    ``exclude_erased`` (default True) drops tombstoned nodes at every layer *before* the
    publish filter, so an erased ancestor item is never distributed even if it was published.
    Extra keyword args are forwarded to :func:`~versum.store.retrieve.docs_from_kg`
    (``include_claims`` / ``include_concepts``). Returned sorted by ``doc_id``.
    """
    return _aggregate(folder, docs_from_kg, exclude_erased=exclude_erased, **kw)


def aggregate_dimensioned_docs(folder, *, exclude_erased: bool = True) -> list:
    """The aggregated dimensioned-subgraph SINK-store Doc set visible from ``folder``.

    The sink-store analogue of :func:`aggregate_docs`: same asymmetric hierarchy (own +
    descendants full, ancestor-published filtered) and same erasure/distribution semantics,
    but over the signed transactions written by
    :class:`versum.ingestion.subgraph.DimensionedSubgraphSink` instead of ``claims.csv`` /
    ``canon.json``. Returned sorted by ``doc_id``.
    """
    return _aggregate(folder, docs_from_dimensioned_store, exclude_erased=exclude_erased)


def from_folder(folder, dense: Dense | None = None, **kw) -> SearchIndex:
    """A :class:`~versum.store.retrieve.SearchIndex` over the aggregated scope of ``folder``.

    ``from_folder(folder).search_similar(query)`` searches own + descendants +
    ancestor-published in one shot. ``dense`` and the ``docs_from_kg`` keyword args behave as
    in :func:`~versum.store.retrieve.from_kg`.
    """
    return SearchIndex(aggregate_docs(folder, **kw), dense=dense)


def from_dimensioned_folder(folder, dense: Dense | None = None, *,
                            exclude_erased: bool = True) -> SearchIndex:
    """A hierarchy- and erasure/distribution-aware :class:`~versum.store.retrieve.SearchIndex`
    over the dimensioned-subgraph SINK store.

    The sink-store companion to :func:`from_folder`:
    ``from_dimensioned_folder(folder).search_similar(query)`` searches own + descendants +
    ancestor-published sink nodes in one shot, excluding erased nodes/sources. ``dense`` behaves
    as in :func:`~versum.store.retrieve.from_dimensioned_store`.
    """
    return SearchIndex(
        aggregate_dimensioned_docs(folder, exclude_erased=exclude_erased), dense=dense)
