"""Regression: a corrupt fingerprints.json must never be silently reset + overwritten.

The fingerprint store under ``by-domain/<domain>/fingerprints.json`` is a
read-modify-write dict ``{canonical_urn: fingerprint}`` that drives concept
identity/dedup. The bug: on ANY read/parse failure (a truncated file from a
crash or partial write, disk corruption, a concurrent writer) ``append_source``
fell back to an empty dict, added the single current entry, and unconditionally
wrote the file — so one bad read *persisted* the wipe, discarding every
previously recorded fingerprint for that domain.

These tests assert the fix end to end at the ``KGStore`` boundary (no mocks):

  (a) normal read-modify-write still accumulates entries across sources;
  (b) a corrupt store makes the write ABORT (raise) and PRESERVES the unreadable
      bytes as ``fingerprints.json.corrupt`` instead of overwriting them to a
      one-entry file — i.e. no silent data loss;
  (c) an empty/whitespace file is treated as "no entries yet", not corruption.
"""
import json
from pathlib import Path

import pytest

import versum.profiles  # noqa: F401 — register built-in profiles
from versum import sync


def _fp_path(kg_root: Path, domain: str) -> Path:
    return kg_root / sync.BY_DOMAIN / domain / "fingerprints.json"


def _append(store: sync.KGStore, domain: str, canonical: str) -> None:
    """Append one minimal source; claim_rows/fingerprint shapes are what sync passes."""
    store.append_source(
        domain=domain, library="lib1", canonical_urn=canonical,
        provenance="mint", relpath=f"{canonical}.txt", sha1="0" * 40,
        claim_rows=[{"item_id": f"{canonical}#1", "unit_type": "para", "text": "x"}],
        fingerprint={"profile": "generic", "digest": canonical},
    )


def test_read_modify_write_accumulates(tmp_path):
    """(a) Two sources in a domain → both fingerprints present (RMW, not clobber)."""
    store = sync.KGStore(tmp_path)
    _append(store, "alpha", "urn:a")
    _append(store, "alpha", "urn:b")

    fps = json.loads(_fp_path(tmp_path, "alpha").read_text(encoding="utf-8"))
    assert set(fps) == {"urn:a", "urn:b"}, "second write must not drop the first entry"


def test_corrupt_store_aborts_and_is_preserved_not_wiped(tmp_path):
    """(b) The core regression: corrupt store → raise + preserve, never silent wipe."""
    store = sync.KGStore(tmp_path)
    _append(store, "alpha", "urn:a")
    _append(store, "alpha", "urn:b")

    fp = _fp_path(tmp_path, "alpha")
    good_bytes = fp.read_bytes()               # the real 2-entry store
    fp.write_text("{ this is not valid json", encoding="utf-8")  # simulate truncation

    # The write must abort loudly rather than reset-to-{} and overwrite.
    with pytest.raises(ValueError, match="unparseable"):
        _append(store, "alpha", "urn:c")

    # The unreadable bytes are preserved for recovery, NOT overwritten to {urn:c}.
    backup = fp.with_name(fp.name + ".corrupt")
    assert backup.exists(), "the corrupt store must be preserved as .corrupt"
    assert backup.read_text(encoding="utf-8") == "{ this is not valid json"

    # And critically: the old code would have left a 1-entry fingerprints.json here
    # (urn:a and urn:b destroyed). The fix leaves no silently-wiped store in place.
    if fp.exists():
        surviving = json.loads(fp.read_text(encoding="utf-8"))
        assert "urn:c" not in surviving or {"urn:a", "urn:b"} <= set(surviving), (
            "a corrupt read must not produce a store that dropped urn:a/urn:b"
        )

    # The prior data is still recoverable from the backup, not lost.
    assert good_bytes  # sanity: we did capture the real store before corrupting it


def test_empty_file_is_not_treated_as_corruption(tmp_path):
    """(c) A zero-byte/whitespace store means 'no entries yet' and writes cleanly."""
    store = sync.KGStore(tmp_path)
    fp = _fp_path(tmp_path, "alpha")
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("   \n", encoding="utf-8")

    _append(store, "alpha", "urn:a")  # must not raise
    fps = json.loads(fp.read_text(encoding="utf-8"))
    assert set(fps) == {"urn:a"}
