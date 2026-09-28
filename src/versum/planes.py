"""Loomground planes in the versum: discovery, the lean plane contract, and entries.

A *plane* (factual, epistemic, deontic, topos, governance, ...) is a separate package that
never imports the versum. It publishes one zero-argument callable under the entry-point
group ``loomground.planes`` (entry name = plane id) that returns a *plane descriptor*::

    {"plane": id, "language_version": str,
     "nd_system": {...},            # an NDSystem document, version == language_version
     "binding": {relation_or_field: <one of the five dimensions>},   # may be {}
     "produce": produce(sentence, context=None) -> [claim, ...],
     "examples": [{"sentence": str, "expected": [claim, ...]}]}      # optional

This module turns descriptors into validated :class:`DescriptorPlane` adapters (fail
closed: a descriptor that does not satisfy the contract raises
:class:`PlaneDescriptorError`), and builds the per-sentence *entries* of a source
(:func:`build_source_entries`): every sentence becomes an entry with an exact span into the
unmodified source text, a five-value 5D position and one dominant dimension
(:mod:`versum.position5d`); each plane claim becomes coordinate assignments and form-slot
bindings on its entry, all validated against the plane's own nD system. Any out-of-
vocabulary value, invalid slot/axis, or non-5D link type raises :class:`PlaneIndexError`
naming plane, axis and value; nothing is dropped or repaired.

No plane vocabulary lives here: axes, closed vocabularies and bindings come only from the
installed plane packages at runtime.

A claim of *any* plane may carry ``spans`` — ``{"content": {"start", "end", "text"}, ...}``
— the plane's own literal offset of its regulated content into the sentence. When a claim
also carries a non-empty ``bearer`` coordinate, this module lowers that content through the
installed ``factual`` plane (``context["subject"]`` = the bearer) and gives it its own
entry, linked from the claim's entry by the ordinary structural "embeds" link. This is how
a deontic norm's content enters the 5D manifold: the deontic plane's own binding is ``{}``
(operators are *ought*, not *is* — see :mod:`versum.deontic` and
``docs/architecture/planes.md``, decision D1 "Round 4"), so a norm's entry gets no 5D
contribution from its operator; it gets one only from the structural "embeds" link to its
content (see the containment step of :func:`build_source_entries`) and from whatever other
plane (e.g. governance) also claims that same sentence span.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from . import position5d as p5
from .nd import Binding, CoordinateAssignment, NDSystem

ENTRY_POINT_GROUP = "loomground.planes"
#: ``index_folder(planes=DISCOVER)`` loads the installed planes (what ``versum index`` does).
DISCOVER = "discover"
_PLANE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_REQUIRED_KEYS = ("plane", "language_version", "nd_system", "binding", "produce")

#: The link type between a sentence entry and an embedded (sub-span) entry.
EMBED_LINK_DIMENSION = "structural"
EMBED_LINK_RELATION = "embeds"
EMBED_LINK_METHOD = "versum-span-containment"

#: Abstention reason code (Phase 0 ontology seam, ``docs/architecture/planes.md``): a
#: norm names a bearer (so it expects its action lowered into its own content entry) but
#: publishes no extractable action span — either no ``spans.content`` at all, or one
#: whose own span invariant does not hold against the sentence. Rather than fabricate a
#: placeholder content/action-type entry, :func:`build_source_entries` abstains: it
#: records this reason in ``out.abstentions`` (written to the store's append-only
#: ``abstentions.jsonl`` by :func:`versum.store.index.index_folder`) and creates no entry
#: for the missing content. The invariant "every deontic action resolves through embeds"
#: (:func:`check_action_embeds_invariant`) applies only to non-abstained rows.
ACTION_IMPLICIT = "ACTION_IMPLICIT"

#: Deletion date (ISO 8601) for :func:`resolve_action_type`, the one compatibility shim a
#: reader still written against the old claims.csv ``embeds``/``embedded_in`` companion
#: columns (reverted — see ``docs/architecture/planes.md``, "Round 7") may call instead of
#: reaching into claims.csv directly. A test enforces this constant does not silently
#: drift past its date.
RESOLVE_ACTION_TYPE_DELETION_DATE = "2027-03-31"


# ── errors ────────────────────────────────────────────────────────
class PlaneError(ValueError):
    """Base class: a plane broke its contract. Indexing fails closed."""


class PlaneDescriptorError(PlaneError):
    """A plane descriptor (or its discovery) does not satisfy the contract."""

    def __init__(self, message: str, *, plane: str | None = None):
        self.plane = plane
        super().__init__(f"plane {plane!r}: {message}" if plane else message)


class PlaneIndexError(PlaneError):
    """A plane's output for a source violates its own nD system or the 5D contract."""

    def __init__(self, message: str, *, plane: str, axis: str | None = None,
                 value: Any = None, source: str | None = None):
        self.plane, self.axis, self.value, self.source = plane, axis, value, source
        where = f" (source {source})" if source else ""
        super().__init__(
            f"plane {plane!r} axis {axis!r} value {value!r}: {message}{where}")


# ── the lean plane contract ───────────────────────────────────────
@runtime_checkable
class PlaneAdapter(Protocol):
    """What the versum needs from a plane — deliberately not the 9-method SystemAdapter."""

    @property
    def plane_id(self) -> str: ...

    @property
    def language_version(self) -> str: ...

    def nd_system(self) -> NDSystem: ...

    def binding(self) -> Mapping[str, str]: ...

    def produce(self, sentence: str, context: dict | None = None) -> list[dict]: ...


@dataclass(frozen=True)
class DescriptorPlane:
    """A :class:`PlaneAdapter` backed by a validated plane descriptor."""

    plane_id: str
    language_version: str
    _system: NDSystem
    _binding: Mapping[str, str]
    _produce: Callable[..., Any]
    _examples: tuple = field(default=())

    def nd_system(self) -> NDSystem:
        return self._system

    def binding(self) -> Mapping[str, str]:
        return self._binding

    def produce(self, sentence: str, context: dict | None = None) -> list[dict]:
        return self._produce(sentence, context)

    def examples(self) -> list[dict]:
        return copy.deepcopy(list(self._examples))

    @classmethod
    def from_descriptor(cls, raw: Any, *, entry_name: str | None = None) -> "DescriptorPlane":
        """Validate a descriptor dict; raise :class:`PlaneDescriptorError` on any breach."""
        if not isinstance(raw, Mapping):
            raise PlaneDescriptorError(
                f"descriptor must be a dict, got {type(raw).__name__}", plane=entry_name)
        plane = raw.get("plane")
        if not isinstance(plane, str) or not _PLANE_ID_RE.match(plane):
            raise PlaneDescriptorError(f"invalid plane id {plane!r}", plane=entry_name)
        if entry_name is not None and entry_name != plane:
            raise PlaneDescriptorError(
                f"entry-point name {entry_name!r} differs from descriptor plane id",
                plane=plane)
        missing = [k for k in _REQUIRED_KEYS if k not in raw]
        if missing:
            raise PlaneDescriptorError(f"descriptor lacks {missing!r}", plane=plane)
        version = raw["language_version"]
        if not isinstance(version, str) or not version:
            raise PlaneDescriptorError(f"invalid language_version {version!r}", plane=plane)
        if not isinstance(raw["nd_system"], Mapping):
            raise PlaneDescriptorError("nd_system must be a dict", plane=plane)
        try:
            system = NDSystem.from_dict(copy.deepcopy(dict(raw["nd_system"]))).validate()
        except (ValueError, TypeError, AttributeError) as exc:
            raise PlaneDescriptorError(f"nd_system does not validate: {exc}",
                                       plane=plane) from exc
        if system.version != version:
            raise PlaneDescriptorError(
                f"nd_system version {system.version!r} != language_version {version!r}",
                plane=plane)
        if system.unknown_values != "reject":
            raise PlaneDescriptorError(
                f"nd_system validation.unknown_values must be 'reject', "
                f"got {system.unknown_values!r}", plane=plane)
        binding = raw["binding"]
        if not isinstance(binding, Mapping):
            raise PlaneDescriptorError("binding must be a dict", plane=plane)
        for key, dim in binding.items():
            if not isinstance(key, str) or not key:
                raise PlaneDescriptorError(f"binding key {key!r} is not a name", plane=plane)
            if not p5.is_dimension(dim):
                raise PlaneDescriptorError(
                    f"binding {key!r} -> {dim!r} is not one of the five dimensions "
                    f"{list(p5.DIMENSIONS)!r}", plane=plane)
        if not callable(raw["produce"]):
            raise PlaneDescriptorError("produce is not callable", plane=plane)
        examples = raw.get("examples", [])
        if examples is None:
            examples = []
        if not isinstance(examples, list) or not all(
                isinstance(e, Mapping) and isinstance(e.get("sentence"), str)
                and isinstance(e.get("expected"), list) for e in examples):
            raise PlaneDescriptorError(
                "examples must be a list of {sentence: str, expected: [claim]}", plane=plane)
        return cls(plane, version, system, MappingProxyType(dict(binding)), raw["produce"],
                   tuple(copy.deepcopy(list(examples))))


def check_adapter(adapter: Any) -> PlaneAdapter:
    """Validate any :class:`PlaneAdapter` implementation against the contract."""
    if isinstance(adapter, DescriptorPlane):
        return adapter
    if not isinstance(adapter, PlaneAdapter):
        raise PlaneDescriptorError(f"{type(adapter).__name__} is not a PlaneAdapter")
    plane = adapter.plane_id
    if not isinstance(plane, str) or not _PLANE_ID_RE.match(plane):
        raise PlaneDescriptorError(f"invalid plane id {plane!r}")
    system = adapter.nd_system()
    try:
        system.validate()
    except ValueError as exc:
        raise PlaneDescriptorError(f"nd_system does not validate: {exc}", plane=plane) from exc
    if system.version != adapter.language_version:
        raise PlaneDescriptorError("nd_system version != language_version", plane=plane)
    for key, dim in adapter.binding().items():
        if not p5.is_dimension(dim):
            raise PlaneDescriptorError(
                f"binding {key!r} -> {dim!r} is not one of the five dimensions", plane=plane)
    return adapter


def _load(item: Any) -> PlaneAdapter:
    if isinstance(item, Mapping):
        return DescriptorPlane.from_descriptor(item)
    if isinstance(item, PlaneAdapter):
        return check_adapter(item)
    if callable(item):
        try:
            raw = item()
        except Exception as exc:  # a plane's own failure must not pass silently
            raise PlaneDescriptorError(
                f"descriptor callable raised {type(exc).__name__}: {exc}") from exc
        return DescriptorPlane.from_descriptor(raw)
    raise PlaneDescriptorError(f"cannot load a plane from {type(item).__name__}")


def load_planes(items: Iterable[Any]) -> list[PlaneAdapter]:
    """Validate an explicit list of descriptors / descriptor callables / adapters.

    This is the injection seam (tests, hosts); ordering is made deterministic by plane id
    and a duplicate id fails closed.
    """
    planes = [_load(item) for item in items]
    return _dedupe_sorted(planes)


def _dedupe_sorted(planes: list[PlaneAdapter]) -> list[PlaneAdapter]:
    seen: set[str] = set()
    for plane in planes:
        if plane.plane_id in seen:
            raise PlaneDescriptorError("registered more than once", plane=plane.plane_id)
        seen.add(plane.plane_id)
    return sorted(planes, key=lambda p: p.plane_id)


def discover_planes(descriptors: Iterable[Any] | None = None) -> list[PlaneAdapter]:
    """The installed planes, from the ``loomground.planes`` entry-point group.

    ``descriptors`` (the injection seam) replaces discovery with an explicit list. Every
    discovered plane is validated; an entry point that fails to load, raises, or returns
    an invalid descriptor aborts with :class:`PlaneDescriptorError` (fail closed).
    """
    if descriptors is not None:
        return load_planes(descriptors)
    eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    planes: list[PlaneAdapter] = []
    for ep in sorted(eps, key=lambda e: e.name):
        try:
            factory = ep.load()
        except Exception as exc:
            raise PlaneDescriptorError(
                f"entry point {ep.value!r} failed to load: {type(exc).__name__}: {exc}",
                plane=ep.name) from exc
        if not callable(factory):
            raise PlaneDescriptorError(f"entry point {ep.value!r} is not callable",
                                       plane=ep.name)
        try:
            raw = factory()
        except Exception as exc:
            raise PlaneDescriptorError(
                f"plane() raised {type(exc).__name__}: {exc}", plane=ep.name) from exc
        planes.append(DescriptorPlane.from_descriptor(raw, entry_name=ep.name))
    return _dedupe_sorted(planes)


# ── sentences ─────────────────────────────────────────────────────
_PARA_BREAK_RE = re.compile(r"\r?\n[ \t]*\r?\n\s*")
# A sentence ends at terminal punctuation (plus closing quotes/brackets) that is followed by
# whitespace NOT leading into a lowercase letter ("e.g. the" does not split), or at a CJK
# full stop / exclamation / question mark.
_SENT_END_RE = re.compile(
    r"[.!?…]+[\"'’”»)\]]*(?=\s)(?!\s+[a-zß-ÿ])"
    r"|[。！？]+[」』）]*")
_HAS_WORD_RE = re.compile(r"\w")


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Deterministic sentence spans ``(start, end)`` into ``text`` (never modified).

    Paragraphs split at blank lines; inside a paragraph a sentence ends at terminal
    punctuation (see ``_SENT_END_RE``). Each span is trimmed of surrounding whitespace, so
    ``text[start:end]`` is the sentence exactly. Segments without a word character are
    not sentences. Independent of any profile marker.
    """
    paras, pos = [], 0
    for m in _PARA_BREAK_RE.finditer(text):
        paras.append((pos, m.start()))
        pos = m.end()
    paras.append((pos, len(text)))
    spans: list[tuple[int, int]] = []
    for p0, p1 in paras:
        seg_start = p0
        cuts = [m.end() for m in _SENT_END_RE.finditer(text, p0, p1)]
        for cut in cuts + [p1]:
            _emit(text, seg_start, cut, spans)
            seg_start = cut
    return spans


def _emit(text: str, a: int, b: int, spans: list) -> None:
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    if b > a and _HAS_WORD_RE.search(text, a, b):
        spans.append((a, b))


def entry_id(source_urn: str, start: int, end: int) -> str:
    """The deterministic entry id: source URN + absolute span, independent of any plane."""
    return "ent-" + hashlib.sha1(f"{source_urn}|{start}|{end}".encode()).hexdigest()[:16]


# ── entries of one source ─────────────────────────────────────────
ENTRY_COLUMNS = ["item_id", "source_urn", "entry_kind", "parent_id", "sentence_index",
                 "span_start", "span_end", "text", *p5.DIMENSIONS, "dominant_dimension",
                 "position_basis", "planes", "relations"]
LINK_COLUMNS = ["link_id", "src_id", "dst_id", "dimension", "relation", "plane", "method"]
#: One JSON object per line in the store's append-only ``abstentions.jsonl`` (see
#: :func:`versum.store.index.index_folder`): a norm the pipeline declined to fabricate a
#: content/action-type entry for, with a reason code (currently only
#: :data:`ACTION_IMPLICIT`) instead of a silently dropped span.
ABSTENTION_COLUMNS = ["abstention_id", "source_urn", "entry_id", "sentence_index",
                      "plane", "reason", "detail"]


@dataclass
class SourceEntries:
    entries: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    assignments: list[CoordinateAssignment] = field(default_factory=list)
    bindings: list[Binding] = field(default_factory=list)
    abstentions: list[dict] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)


def _json_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _hid(prefix: str, *parts: Any) -> str:
    return prefix + hashlib.sha1("|".join(_json_key(p) for p in parts).encode()) \
        .hexdigest()[:16]


def _record_abstention(out: "SourceEntries", *, source_urn: str, entry_id_: str,
                       sent_idx: int, plane: str, reason: str, detail: str) -> None:
    """Append one abstention record — never a placeholder entry — to ``out.abstentions``.

    Deterministic id (source + entry + reason), so a re-index of the same source never
    duplicates a record. See :data:`ACTION_IMPLICIT` and
    :func:`versum.store.index.index_folder`'s ``abstentions.jsonl``.
    """
    aid = _hid("abst-", source_urn, entry_id_, reason)
    out.abstentions.append({
        "abstention_id": aid, "source_urn": source_urn, "entry_id": entry_id_,
        "sentence_index": sent_idx, "plane": plane, "reason": reason, "detail": detail,
    })


def _span(raw: Any, length: int, *, plane: str, source: str, what: str) -> tuple[int, int]:
    if (not isinstance(raw, (list, tuple)) or len(raw) != 2
            or not all(isinstance(x, int) and not isinstance(x, bool) for x in raw)
            or not 0 <= raw[0] < raw[1] <= length):
        raise PlaneIndexError(f"{what} {raw!r} is not a [start, end] span inside the "
                              f"sentence (length {length})", plane=plane, source=source)
    return raw[0], raw[1]


def _values(axis, value) -> list:
    """Expand a list value on a many-valued non-interval axis to one value each."""
    if (isinstance(value, list) and axis is not None and axis.cardinality == "many"
            and axis.value_type != "interval"):
        return list(value)
    return [value]


def build_source_entries(text: str, source_urn: str, planes: Iterable[PlaneAdapter], *,
                         context: dict | None = None, source_id: str | None = None,
                         ) -> SourceEntries:
    """Entries, links, assignments and bindings for one source — all or nothing.

    Pure: reads ``text`` and calls each plane's producer once per sentence; raises
    :class:`PlaneIndexError` on the first contract violation, before anything is returned.
    """
    planes = list(planes)
    source_id = source_id or source_urn
    out = SourceEntries()
    entries: dict[tuple[int, int], dict] = {}
    contrib: dict[str, dict[str, int]] = {}
    seen_assign: set[str] = set()
    seen_bind: set[str] = set()
    seen_link: set[str] = set()

    def get_entry(span: tuple[int, int], kind: str, sent_idx: int) -> dict:
        e = entries.get(span)
        if e is None:
            e = {"item_id": entry_id(source_urn, *span), "source_urn": source_urn,
                 "entry_kind": kind, "parent_id": "", "sentence_index": sent_idx,
                 "span_start": span[0], "span_end": span[1], "text": text[span[0]:span[1]],
                 "_planes": set(), "_relations": set()}
            entries[span] = e
            contrib[e["item_id"]] = p5.zero_contributions()
        return e

    def add_link(src: dict, dst: dict, dim: str, relation: str, plane: str, method: str):
        lid = _hid("enl-", src["item_id"], dst["item_id"], dim, relation, plane)
        if lid not in seen_link:
            seen_link.add(lid)
            out.links.append({"link_id": lid, "src_id": src["item_id"],
                              "dst_id": dst["item_id"], "dimension": dim,
                              "relation": relation, "plane": plane, "method": method})

    for sent_idx, (s0, s1) in enumerate(sentence_spans(text)):
        sentence = text[s0:s1]
        sent_entry = get_entry((s0, s1), "sentence", sent_idx)
        pending_links: list[tuple] = []
        all_claims: list[tuple[PlaneAdapter, Mapping]] = []
        for plane in planes:
            pid = plane.plane_id
            system = plane.nd_system()
            bind = plane.binding()
            # Fail closed (rule 6) on the invariant behind decision D1: the deontic plane
            # is the OUGHT plane — an operator (O/P/F) is a normative force, not a fact on
            # the 5D manifold, so its binding() is contractually always {} (see
            # docs/architecture/planes.md and the deontic plane's own nd_system()
            # ["describes"]). The generic contribution code just below
            # (`if relation in bind: c[bind[relation]] += 1`) has no way to tell an
            # operator's relation from any other plane's; it would silently start adding
            # 5D contributions for O/P/F the moment a deontic descriptor ever published a
            # non-empty binding. Refuse instead of silently applying it: a non-empty
            # binding from the plane registered as "deontic" is a contract breach, not
            # data to project.
            if pid == "deontic" and bind:
                raise PlaneIndexError(
                    f"the deontic plane published a non-empty binding {dict(bind)!r}; "
                    "an operator (O/P/F) is OUGHT, not a fact on the 5D manifold (D1) — "
                    "refusing to let any operator contribute to 5D under any name",
                    plane=pid, source=source_urn)
            try:
                claims = plane.produce(sentence, copy.deepcopy(context))
            except Exception as exc:
                raise PlaneIndexError(f"producer raised {type(exc).__name__}: {exc}",
                                      plane=pid, source=source_urn) from exc
            if not isinstance(claims, list):
                raise PlaneIndexError(
                    f"producer returned {type(claims).__name__}, not a list",
                    plane=pid, source=source_urn)
            for claim in claims:
                _apply_claim(claim, plane=plane, system=system, bind=bind,
                             sentence=sentence, s0=s0, sent_idx=sent_idx,
                             source_urn=source_urn, source_id=source_id,
                             get_entry=get_entry, contrib=contrib, out=out,
                             seen_assign=seen_assign, seen_bind=seen_bind,
                             pending_links=pending_links)
            all_claims.extend((plane, c) for c in claims if isinstance(c, Mapping))
        # A norm's content: no plane's binding puts an ought (an operator) on the 5D
        # manifold (Round 4) — a norm's content enters 5D only through what it factually
        # says. Any claim (of any plane; no plane id is named here) that carries
        # ``spans.content`` — the plane's own literal offset of its regulated content into
        # this sentence, ``sentence[start:end] == text`` — and a non-empty ``bearer``
        # coordinate has that content lowered through the installed ``factual`` plane, if
        # one is installed, with ``context["subject"]`` set to the bearer. The factual
        # producer runs once per such span; the resulting claim(s) are applied exactly as
        # any plane's own claim (:func:`_apply_claim`) at their span shifted into the
        # sentence, so the content becomes its own entry with its own factual 5D
        # contribution. The containment step below then links norm -> content with the
        # ordinary structural "embeds" link — the *only* channel through which the norm's
        # entry itself receives a 5D contribution now that operators bind to nothing (see
        # docs/architecture/planes.md, decision D1 note "Round 4").
        factual_plane = next((p for p in planes if p.plane_id == "factual"), None)
        if factual_plane is not None:
            for norm_plane, claim in all_claims:
                spans = claim.get("spans")
                content = spans.get("content") if isinstance(spans, Mapping) else None
                coords = claim.get("coordinates")
                bearer = coords.get("bearer") if isinstance(coords, Mapping) else None
                if not isinstance(bearer, str) or not bearer:
                    continue  # not a norm naming a bearer; nothing of this kind to lower
                norm_cs0, norm_ce0 = claim.get("span")
                norm_entry_id_for_abstention = entry_id(
                    source_urn, s0 + norm_cs0, s0 + norm_ce0)
                if not isinstance(content, Mapping):
                    _record_abstention(
                        out, source_urn=source_urn, entry_id_=norm_entry_id_for_abstention,
                        sent_idx=sent_idx, plane=norm_plane.plane_id,
                        reason=ACTION_IMPLICIT,
                        detail="claim names a bearer but publishes no spans.content — "
                               "no extractable action span")
                    continue
                c0, c1, ctext = (content.get("start"), content.get("end"),
                                 content.get("text"))
                if not (isinstance(c0, int) and isinstance(c1, int)
                        and isinstance(ctext, str) and 0 <= c0 < c1 <= len(sentence)
                        and sentence[c0:c1] == ctext):
                    # abstain: the plane's own span invariant does not hold here — treated
                    # the same as no action span at all, never a fabricated placeholder.
                    _record_abstention(
                        out, source_urn=source_urn, entry_id_=norm_entry_id_for_abstention,
                        sent_idx=sent_idx, plane=norm_plane.plane_id,
                        reason=ACTION_IMPLICIT,
                        detail="claim's spans.content does not satisfy its own span "
                               "invariant against the sentence")
                    continue
                norm_cs, norm_ce = claim.get("span")
                norm_kind = "sentence" if (norm_cs, norm_ce) == (0, len(sentence)) \
                    else "embedded"
                norm_entry = get_entry((s0 + norm_cs, s0 + norm_ce), norm_kind, sent_idx)
                try:
                    fclaims = factual_plane.produce(ctext, {"subject": bearer})
                except Exception as exc:
                    raise PlaneIndexError(
                        f"factual producer raised {type(exc).__name__}: {exc}",
                        plane="factual", source=source_urn) from exc
                if not isinstance(fclaims, list):
                    raise PlaneIndexError(
                        "factual producer returned a non-list for a norm's content",
                        plane="factual", source=source_urn)
                for fclaim in fclaims:
                    if not isinstance(fclaim, Mapping):
                        continue
                    fspan = fclaim.get("span")
                    if not (isinstance(fspan, (list, tuple)) and len(fspan) == 2):
                        continue
                    remapped = dict(fclaim)
                    remapped["span"] = [c0 + fspan[0], c0 + fspan[1]]
                    _apply_claim(remapped, plane=factual_plane,
                                 system=factual_plane.nd_system(),
                                 bind=factual_plane.binding(), sentence=sentence, s0=s0,
                                 sent_idx=sent_idx, source_urn=source_urn,
                                 source_id=source_id, get_entry=get_entry, contrib=contrib,
                                 out=out, seen_assign=seen_assign, seen_bind=seen_bind,
                                 pending_links=pending_links)
                    # the content entry is linked from the NORM's own entry directly (not
                    # whatever entry the general containment step below would otherwise
                    # pick as the smallest enclosing span, e.g. another plane's own claim
                    # that happens to overlap the same text): the norm -> content
                    # relationship is asserted here, once, by this claim's own bearer/spans,
                    # and it is set before the generic containment step runs so that step
                    # leaves it alone (it never re-parents an entry that already has one).
                    content_span = (s0 + c0, s0 + c1)
                    content_kind = "sentence" if content_span == (s0, s1) else "embedded"
                    content_entry = get_entry(content_span, content_kind, sent_idx)
                    if not content_entry["parent_id"] \
                            and content_entry is not norm_entry:
                        content_entry["parent_id"] = norm_entry["item_id"]
                        add_link(norm_entry, content_entry, EMBED_LINK_DIMENSION,
                                 EMBED_LINK_RELATION, "", EMBED_LINK_METHOD)
                        contrib[norm_entry["item_id"]][EMBED_LINK_DIMENSION] += 1
                    # The norm's own coordinate that named the content AS TEXT (e.g. a
                    # deontic norm's `action` axis) is re-pointed at the content/action-type
                    # entry's item_id: the claim's own coordinate whose value is exactly the
                    # content span's text is the one being lowered, so it is that coordinate
                    # — not a hardcoded axis name — that stops asserting the literal text a
                    # second time and instead carries a concept reference to the entry the
                    # text became (its own axis stays `concept_reference`/entity-open; see
                    # e.g. the deontic plane's own nd_system()["describes"], Round 5: "the
                    # action axis ... is a reference (item_id / concept reference) to the
                    # action-type entry ..., never asserting the action into the norm's own
                    # coordinates" as literal text). The claim as logged in
                    # entry_claims.jsonl is untouched (rule 4: it reproduces produce()
                    # field for field); only the derived CoordinateAssignment/Binding are
                    # re-pointed.
                    content_axis = _content_reference_axis(claim, ctext)
                    if content_axis is not None:
                        _repoint_axis_to_reference(
                            norm_entry_id=norm_entry["item_id"], claim=claim,
                            axis_id=content_axis, reference=content_entry["item_id"],
                            system=norm_plane.nd_system(), source_id=source_id, out=out,
                            seen_assign=seen_assign, seen_bind=seen_bind,
                            plane_id=norm_plane.plane_id)
        # link targets first, so every entry of this sentence exists before parents are set
        resolved = []
        for src, dst_span, dim, relation, pid, method in pending_links:
            kind = "sentence" if dst_span == (s0, s1) else "embedded"
            resolved.append((src, get_entry(dst_span, kind, sent_idx), dim, relation, pid,
                             method))
        # parent of each embedded entry: the smallest strictly enclosing entry of this
        # sentence (else the sentence entry); linked by a structural "embeds" link, which
        # also contributes 1 to the *parent's* own structural 5D position — an entry that
        # structurally contains another carries that much structural information itself.
        own = sorted((sp for sp in entries if s0 <= sp[0] and sp[1] <= s1),
                     key=lambda sp: (sp[0], -sp[1]))
        for sp in own:
            e = entries[sp]
            if e is sent_entry or e["parent_id"]:
                continue
            enclosing = [o for o in own if o != sp and o[0] <= sp[0] and sp[1] <= o[1]]
            parent = entries[min(enclosing, key=lambda o: (o[1] - o[0], o))] \
                if enclosing else sent_entry
            e["parent_id"] = parent["item_id"]
            add_link(parent, e, EMBED_LINK_DIMENSION, EMBED_LINK_RELATION, "",
                     EMBED_LINK_METHOD)
            contrib[parent["item_id"]][EMBED_LINK_DIMENSION] += 1
        for src, dst, dim, relation, pid, method in resolved:
            add_link(src, dst, dim, relation, pid, method)

    for span in sorted(entries):
        e = entries[span]
        c = contrib[e["item_id"]]
        row = {k: v for k, v in e.items() if not k.startswith("_")}
        row.update(p5.position(c))
        row["dominant_dimension"] = p5.dominant(c)
        row["position_basis"] = p5.basis(c)
        row["planes"] = ";".join(sorted(e["_planes"]))
        row["relations"] = ";".join(sorted(e["_relations"]))
        out.entries.append(row)
    return out


def _content_reference_axis(claim: Mapping, content_text: str) -> str | None:
    """The claim's own coordinate whose value is exactly ``content_text`` — the coordinate
    that asserted the norm's content as literal text (e.g. a deontic norm's ``action``
    axis) and must instead end up a concept reference to the content/action-type entry
    that text became (:func:`_repoint_axis_to_reference`). No axis name or plane id is
    named here: any plane whose claim carries a coordinate equal, character for character,
    to its own ``spans.content`` text is naming that coordinate as the content, whatever it
    calls the axis. ``None`` when no coordinate matches (nothing to re-point)."""
    coords = claim.get("coordinates")
    if not isinstance(coords, Mapping):
        return None
    for axis_id, value in coords.items():
        if value == content_text:
            return axis_id
    return None


def _repoint_axis_to_reference(*, norm_entry_id: str, claim: Mapping, axis_id: str,
                               reference: str, system: NDSystem, source_id: str,
                               out: SourceEntries, seen_assign: set[str],
                               seen_bind: set[str], plane_id: str = "") -> None:
    """Replace the norm claim's own coordinate assignment for ``axis_id`` — as produced,
    the literal content text — with a reference to the content/action-type entry that text
    became (``reference``, its ``item_id``). Never both: the CoordinateAssignment and
    Binding rows :func:`_apply_claim` already wrote for this entry/axis (from the claim's
    own, unmodified coordinate value) are removed and replaced; the claim as logged in
    ``entry_claims.jsonl`` is untouched, so rule 4 (round-trip fidelity to ``produce()``)
    still holds — only the derived nD rows change. Method ``versum-action-type-reference``
    marks the assignment as versum's own derivation, not the plane's.
    """
    METHOD_REF = "versum-action-type-reference"
    removed_ids = {a.assignment_id for a in out.assignments
                  if a.subject_id == norm_entry_id and a.system_id == system.system_id
                  and a.axis_id == axis_id}
    if not removed_ids:
        return  # nothing was assigned for this axis (e.g. the value was empty); nothing to redo
    out.assignments[:] = [a for a in out.assignments if a.assignment_id not in removed_ids]
    out.bindings[:] = [b for b in out.bindings
                       if not (b.claim_id == norm_entry_id and b.axis_id == axis_id
                               and b.assignment_id in removed_ids)]
    for aid in removed_ids:
        seen_assign.discard(aid)
    aid = _hid("nda-", norm_entry_id, system.system_id, system.version, axis_id, reference,
              "action-type-reference")
    assignment = CoordinateAssignment(
        subject_id=norm_entry_id, system_id=system.system_id, system_version=system.version,
        axis_id=axis_id, value=reference, source_id=source_id, method=METHOD_REF,
        verification="candidate", assignment_id=aid)
    errors = assignment.violations(system)
    if errors:
        raise PlaneIndexError("; ".join(errors), plane=plane_id or system.system_id,
                              axis=axis_id, value=reference, source=source_id)
    seen_assign.add(aid)
    out.assignments.append(assignment)
    slots = claim.get("slots") or {}
    relation = claim.get("relation", "") if isinstance(claim.get("relation"), str) else ""
    for slot, ax in (slots.items() if isinstance(slots, Mapping) else ()):
        if ax != axis_id:
            continue
        bid = _hid("ndb-", norm_entry_id, slot, aid, relation)
        binding = Binding(claim_id=norm_entry_id, form_slot=str(slot),
                          semantic_role=relation, assignment_id=aid, axis_id=axis_id,
                          value=reference, source_id=source_id, method=METHOD_REF,
                          verification="candidate", binding_id=bid)
        errors = binding.violations(system)
        if errors:
            raise PlaneIndexError("; ".join(errors), plane=plane_id or system.system_id,
                                  axis=axis_id, value=reference, source=source_id)
        seen_bind.add(bid)
        out.bindings.append(binding)


def _apply_claim(claim, *, plane, system: NDSystem, bind, sentence, s0, sent_idx,
                 source_urn, source_id, get_entry, contrib, out, seen_assign, seen_bind,
                 pending_links) -> None:
    pid = plane.plane_id
    if not isinstance(claim, Mapping):
        raise PlaneIndexError(f"claim must be a dict, got {type(claim).__name__}",
                              plane=pid, source=source_urn)
    try:  # the claim is persisted as produced; it must serialise before anything is written
        json.dumps(claim, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise PlaneIndexError(f"claim is not JSON-serialisable: {exc}", plane=pid,
                              source=source_urn) from exc
    relation = claim.get("relation")
    if not isinstance(relation, str) or not relation:
        raise PlaneIndexError("claim has no relation", plane=pid, value=relation,
                              source=source_urn)
    method = claim.get("method")
    if not isinstance(method, str) or not method:
        raise PlaneIndexError("claim has no method", plane=pid, value=method,
                              source=source_urn)
    cs, ce = _span(claim.get("span"), len(sentence), plane=pid, source=source_urn,
                   what="claim span")
    span = (s0 + cs, s0 + ce)
    kind = "sentence" if (cs, ce) == (0, len(sentence)) else "embedded"
    entry = get_entry(span, kind, sent_idx)
    item_id = entry["item_id"]
    entry["_planes"].add(pid)
    entry["_relations"].add(f"{pid}:{relation}")
    coords = claim.get("coordinates", {}) or {}
    slots = claim.get("slots", {}) or {}
    if not isinstance(coords, Mapping) or not isinstance(slots, Mapping):
        raise PlaneIndexError("coordinates and slots must be dicts", plane=pid,
                              source=source_urn)

    # 5D contributions: the relation's binding, and each bound coordinate field.
    c = contrib[item_id]
    if relation in bind:
        c[bind[relation]] += 1
    for axis_id in sorted(coords):
        if axis_id in bind:
            c[bind[axis_id]] += 1

    by_axis: dict[str, list[CoordinateAssignment]] = {}
    for axis_id in sorted(coords, key=str):
        axis = system.axes.get(axis_id)
        for value in _values(axis, coords[axis_id]):
            a = CoordinateAssignment(
                subject_id=item_id, system_id=system.system_id,
                system_version=system.version, axis_id=axis_id, value=value,
                source_id=source_id, method=method, verification="candidate")
            errors = a.violations(system)
            if errors:
                raise PlaneIndexError("; ".join(errors), plane=pid, axis=axis_id,
                                      value=value, source=source_urn)
            try:
                json.dumps(value, ensure_ascii=False, sort_keys=True)
            except (TypeError, ValueError) as exc:
                raise PlaneIndexError("value is not JSON-serialisable", plane=pid,
                                      axis=axis_id, value=value, source=source_urn) from exc
            aid = _hid("nda-", item_id, system.system_id, system.version, axis_id, value)
            a = replace(a, assignment_id=aid)
            by_axis.setdefault(axis_id, []).append(a)
            if aid not in seen_assign:
                seen_assign.add(aid)
                out.assignments.append(a)

    for slot in sorted(slots, key=str):
        axis_id = slots[slot]
        if axis_id not in by_axis:
            raise PlaneIndexError(
                f"slot {slot!r} binds axis {axis_id!r}, which the claim gives no value",
                plane=pid, axis=axis_id if isinstance(axis_id, str) else None,
                value=None, source=source_urn)
        for a in by_axis[axis_id]:
            b = Binding(claim_id=item_id, form_slot=str(slot), semantic_role=relation,
                        assignment_id=a.assignment_id, axis_id=axis_id, value=a.value,
                        source_id=source_id, method=method, verification="candidate")
            errors = b.violations(system)
            if errors:
                raise PlaneIndexError("; ".join(errors) + f" (form_slot {slot!r})",
                                      plane=pid, axis=axis_id, value=a.value,
                                      source=source_urn)
            bid = _hid("ndb-", item_id, slot, a.assignment_id, relation)
            if bid not in seen_bind:
                seen_bind.add(bid)
                out.bindings.append(replace(b, binding_id=bid))

    links = claim.get("links", []) or []
    if not isinstance(links, list):
        raise PlaneIndexError("links must be a list", plane=pid, source=source_urn)
    for link in links:
        if not isinstance(link, Mapping):
            raise PlaneIndexError("link must be a dict", plane=pid, source=source_urn)
        dim = link.get("type")
        if not p5.is_dimension(dim):
            raise PlaneIndexError(
                f"link type is not one of the five dimensions {list(p5.DIMENSIONS)!r}",
                plane=pid, axis="type", value=dim, source=source_urn)
        rel = link.get("relation")
        if not isinstance(rel, str) or not rel:
            raise PlaneIndexError("link has no relation", plane=pid, value=rel,
                                  source=source_urn)
        ts, te = _span(link.get("to_span"), len(sentence), plane=pid, source=source_urn,
                       what="link to_span")
        pending_links.append((entry, (s0 + ts, s0 + te), dim, rel, pid, method))

    out.claims.append({"item_id": item_id, "source_urn": source_urn, "plane": pid,
                       "language_version": plane.language_version,
                       "sentence_span": [s0, s0 + len(sentence)],
                       "claim": _json_safe(claim)})


def _json_safe(obj):
    if isinstance(obj, Mapping):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return copy.deepcopy(obj)


# ── reading entries back ──────────────────────────────────────────
def entry_coordinates(entry: Mapping, assignments: Iterable[Mapping]) -> list[dict]:
    """All coordinates that apply to ``entry``: its own plane assignments plus the
    source-level core coordinates (jurisdiction, time, ...) of its source, which apply to
    every entry of that source."""
    ids = {entry["item_id"], entry["source_urn"]}
    return [dict(a) for a in assignments if a.get("subject_id") in ids]


# ── compatibility shim (Phase 0 ontology seam) ─────────────────────
def resolve_action_type(versum_dir, claim_entry_id: str) -> dict | None:
    """TEMPORARY compatibility shim — delete by :data:`RESOLVE_ACTION_TYPE_DELETION_DATE`
    (``2027-03-31``; a test enforces this constant does not drift).

    A norm's action type is no longer readable off ``claims.csv`` (the companion
    ``embeds``/``embedded_in`` row design was reverted — see
    ``docs/architecture/planes.md``, "Round 7"): it lives only as a not-asserted entry in
    the entry model, linked from the norm's own entry by the structural "embeds" relation
    (:data:`EMBED_LINK_RELATION`). A reader still written against the old claims.csv
    columns should call this instead of reaching into claims.csv directly.

    ``versum_dir`` is a store's ``.versum`` directory (or any directory carrying its own
    ``entries.csv`` / ``entry_links.csv`` in that shape). Returns the action-type entry
    row (a dict, as read off ``entries.csv``) that ``claim_entry_id`` embeds, or ``None``
    when it has no outgoing "embeds" link — e.g. an abstained :data:`ACTION_IMPLICIT`
    norm, or a claim that names no action at all. Never fabricates a placeholder.

    This function must not grow a second call site: every reader migrates through this
    one shim, so its deletion removes the whole compatibility surface in one move.
    """
    versum_dir = Path(versum_dir)
    entries = _load_entries_csv(versum_dir / "entries.csv")
    dst_id = None
    links_path = versum_dir / "entry_links.csv"
    if links_path.exists():
        import csv as _csv
        with open(links_path, newline="", encoding="utf-8") as fh:
            for row in _csv.DictReader(fh):
                if (row.get("src_id") == claim_entry_id
                        and row.get("relation") == EMBED_LINK_RELATION
                        and row.get("dimension") == EMBED_LINK_DIMENSION):
                    dst_id = row.get("dst_id")
                    break
    if dst_id is None:
        return None
    return entries.get(dst_id)


def _load_entries_csv(path) -> dict[str, dict]:
    if not path.exists():
        return {}
    import csv as _csv
    with open(path, newline="", encoding="utf-8") as fh:
        return {row["item_id"]: dict(row) for row in _csv.DictReader(fh)}


def _load_jsonl(path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def check_action_embeds_invariant(versum_dir) -> list[str]:
    """Verify "every deontic action resolves through embeds" over an indexed store.

    Reads ``entry_claims.jsonl``, ``entry_links.csv`` and ``abstentions.jsonl`` under
    ``versum_dir`` (a store's ``.versum`` directory). For every logged claim that names a
    non-empty ``bearer`` coordinate (a norm expecting its action lowered into its own
    content entry) and is NOT recorded in ``abstentions.jsonl`` (an abstained row has no
    content entry by design — see :data:`ACTION_IMPLICIT`), there must be an outgoing
    "embeds" link (dimension :data:`EMBED_LINK_DIMENSION`) from that claim's own entry.

    Returns a list of violation strings; an empty list means the invariant holds. Never
    raises on a well-formed but empty store (no claims, no links, no abstentions) — the
    invariant holds vacuously.
    """
    versum_dir = Path(versum_dir)
    claims = _load_jsonl(versum_dir / "entry_claims.jsonl")
    abstained_entry_ids = {rec.get("entry_id") for rec in
                           _load_jsonl(versum_dir / "abstentions.jsonl")}
    embed_srcs: set[str] = set()
    links_path = versum_dir / "entry_links.csv"
    if links_path.exists():
        import csv as _csv
        with open(links_path, newline="", encoding="utf-8") as fh:
            for row in _csv.DictReader(fh):
                if (row.get("relation") == EMBED_LINK_RELATION
                        and row.get("dimension") == EMBED_LINK_DIMENSION):
                    embed_srcs.add(row.get("src_id"))
    violations = []
    for rec in claims:
        claim = rec.get("claim") or {}
        coords = claim.get("coordinates") if isinstance(claim, Mapping) else None
        bearer = coords.get("bearer") if isinstance(coords, Mapping) else None
        if not isinstance(bearer, str) or not bearer:
            continue  # not a norm naming a bearer; the invariant does not apply
        entry_id_ = rec.get("item_id")
        if entry_id_ in abstained_entry_ids:
            continue  # abstained (ACTION_IMPLICIT or similar): no content entry by design
        if entry_id_ not in embed_srcs:
            violations.append(
                f"claim entry {entry_id_!r} (plane {rec.get('plane')!r}) names a bearer "
                "but has no outgoing 'embeds' link and is not recorded in "
                "abstentions.jsonl")
    return violations
