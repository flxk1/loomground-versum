"""Phase 3 loop-6: the single write door into a Versum, at the engine level.

Asserts/documents that the ``.versum`` store is WRITTEN only through the capture guard
(:mod:`versum.write`) and ``index_folder`` — no other core module is a write door into it.
Materialize (loop 7) is additive: it READS the store and writes a separate canonical export,
so it must never create or mutate the ``.versum`` store. Versum is standalone; retired
external product writers are neither alternate write doors nor release dependencies.
"""
from pathlib import Path

from versum.write import capture_folder
from versum.store.index import index_folder
from versum.materialize import materialize
import versum.profiles  # noqa: F401 — register built-ins


def _store_bytes(v: Path) -> dict:
    return {p.relative_to(v).as_posix(): p.read_bytes()
            for p in sorted(v.rglob("*")) if p.is_file()}


def test_index_folder_is_a_write_door(tmp_path):
    (tmp_path / "a.md").write_text(
        "A widget is defined as a thing. A widget causes value.\n", encoding="utf-8")
    assert not (tmp_path / ".versum").exists()      # store absent before the door opens
    index_folder(tmp_path, "generic")
    assert (tmp_path / ".versum" / "claims.csv").exists()


def test_capture_routes_through_index_folder(tmp_path):
    """capture_folder ends by calling index_folder once — capture writes the store only via it."""
    (tmp_path / "a.md").write_text(
        "A widget is defined as a thing. A widget causes value.\n", encoding="utf-8")
    res = capture_folder(tmp_path, "generic")
    # the capture result carries the index manifest → capture materialised the store through
    # the SAME index_folder door, not a parallel write path.
    assert "index" in res and res["index"]["n_sources"] >= 1
    assert (tmp_path / ".versum" / "claims.csv").exists()


def test_materialize_is_not_a_write_door_into_the_store(tmp_path):
    (tmp_path / "a.md").write_text(
        "A widget is defined as a thing. A widget causes value.\n", encoding="utf-8")
    index_folder(tmp_path, "generic")
    v = tmp_path / ".versum"
    before = _store_bytes(v)
    materialize(tmp_path, tmp_path / "out")     # reads the store, writes elsewhere
    assert _store_bytes(v) == before            # store byte-for-byte unchanged
