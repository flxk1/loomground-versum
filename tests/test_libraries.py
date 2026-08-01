"""Phase 1 libraries registry — mapping, byte resolution, unique-namespace invariant."""
import pytest

from versum.libraries import LibrariesRegistry, LibraryError


def test_resolve_is_root_plus_relpath(tmp_path):
    libs = LibrariesRegistry({
        "dls": {"root_path": str(tmp_path / "Example Corpus"),
                "urn_namespace": "dls"},
    })
    rel = "knowledge_library/ai_act_and_regulation/2021/Foo.pdf"
    got = libs.resolve("dls", rel)
    assert got == (tmp_path / "Example Corpus" / rel).resolve()
    assert libs.namespace_for("dls") == "dls"


def test_relative_path_required(tmp_path):
    libs = LibrariesRegistry({"dls": {"root_path": str(tmp_path), "urn_namespace": "dls"}})
    with pytest.raises(LibraryError):
        libs.resolve("dls", "/etc/passwd")


def test_duplicate_namespace_rejected(tmp_path):
    libs = LibrariesRegistry({"a": {"root_path": str(tmp_path / "a"),
                                    "urn_namespace": "shared"}})
    with pytest.raises(LibraryError):
        libs.add("b", str(tmp_path / "b"), "shared")   # same namespace -> reject


def test_unique_namespaces_accepted(tmp_path):
    libs = LibrariesRegistry()
    libs.add("a", str(tmp_path / "a"), "ns-a")
    libs.add("b", str(tmp_path / "b"), "ns-b")
    assert set(libs.ids()) == {"a", "b"}
    assert libs.namespace_for("a") != libs.namespace_for("b")


def test_empty_namespace_rejected(tmp_path):
    with pytest.raises(LibraryError):
        LibrariesRegistry({"a": {"root_path": str(tmp_path), "urn_namespace": ""}})


def test_roundtrip_save_load(tmp_path):
    libs = LibrariesRegistry({
        "a": {"root_path": str(tmp_path / "a"), "urn_namespace": "ns-a"},
        "b": {"root_path": str(tmp_path / "b"), "urn_namespace": "ns-b"},
    })
    p = tmp_path / "libraries.json"
    libs.save(p)
    back = LibrariesRegistry.load(p)
    assert back.to_dict() == libs.to_dict()
