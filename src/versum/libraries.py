"""versum/libraries.py — the libraries registry (Phase 1, loops 2 & 8).

A *library* is a named collection of source files rooted at some directory, with its own
globally-unique URN namespace. A file's bytes are resolved as ``root_path + relpath``; a
file's identity is minted under the library's ``urn_namespace`` (loop 8: the namespace is
sourced from the library, NOT baked into a profile constant), so the SAME relpath under two
libraries with different namespaces yields two distinct URNs.

This module owns only the mapping ``library-id -> {root_path, urn_namespace}`` and the byte
resolution; it mints no URNs itself (that stays in ``identity``/``urn``) and reads no domain
vocabulary. Namespaces MUST be unique across libraries — two libraries sharing a namespace
would collide their URN spaces, defeating the whole point. No network.
"""
from __future__ import annotations

import json
from pathlib import Path


class LibraryError(ValueError):
    """A libraries-registry invariant was violated (e.g. a duplicate namespace)."""


class LibrariesRegistry:
    """A small map ``library-id -> {root_path, urn_namespace}`` with unique namespaces.

    Construct from a dict, ``from_dict`` or ``load`` (JSON). Every mutation re-checks the
    global namespace-uniqueness invariant, so an invalid registry can never exist.
    """

    def __init__(self, libraries: dict | None = None):
        self._libs: dict[str, dict] = {}
        for lib_id, spec in (libraries or {}).items():
            self.add(lib_id, spec["root_path"], spec["urn_namespace"])

    # ── mutation ────────────────────────────────────────────────
    def add(self, library_id: str, root_path, urn_namespace: str) -> None:
        """Register a library; raise ``LibraryError`` if its namespace is already taken."""
        if not library_id:
            raise LibraryError("library_id must be non-empty")
        if not urn_namespace:
            raise LibraryError(f"library {library_id!r} has an empty urn_namespace")
        for other_id, spec in self._libs.items():
            if other_id != library_id and spec["urn_namespace"] == urn_namespace:
                raise LibraryError(
                    f"urn_namespace {urn_namespace!r} already used by library "
                    f"{other_id!r}; namespaces must be globally unique")
        self._libs[library_id] = {
            "root_path": str(root_path), "urn_namespace": urn_namespace}

    # ── lookup ──────────────────────────────────────────────────
    def __contains__(self, library_id: str) -> bool:
        return library_id in self._libs

    def ids(self) -> list[str]:
        return list(self._libs)

    def get(self, library_id: str) -> dict:
        """Return ``{root_path, urn_namespace}`` for a library (KeyError if unknown)."""
        return self._libs[library_id]

    def namespace_for(self, library_id: str) -> str:
        """The URN namespace to mint identities under for this library."""
        return self._libs[library_id]["urn_namespace"]

    def root_for(self, library_id: str) -> Path:
        return Path(self._libs[library_id]["root_path"])

    def resolve(self, library_id: str, relpath: str) -> Path:
        """Resolve a source's bytes: ``root_path + relpath`` -> absolute path.

        The path is returned whether or not it exists on disk; existence is the caller's
        concern (a registry row may point at a not-yet-arrived file).
        """
        rel = Path(str(relpath))
        if rel.is_absolute():
            raise LibraryError(f"relpath must be relative, got {relpath!r}")
        return (self.root_for(library_id) / rel).resolve()

    # ── serialisation ───────────────────────────────────────────
    def to_dict(self) -> dict:
        return {k: dict(v) for k, v in self._libs.items()}

    @classmethod
    def from_dict(cls, data: dict) -> "LibrariesRegistry":
        return cls(data)

    def save(self, path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "LibrariesRegistry":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
