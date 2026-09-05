"""`--extra-profile-module` registers a HOST-defined profile before the id is resolved.

A host vertical's Profile lives outside versum's built-in package and self-registers on import.
Naming its module on the CLI must import+register it so `--profile <host-id>` resolves, without
versum core importing any host code (domain-neutral seam).
"""
import sys
from pathlib import Path

from versum.__main__ import main
from versum.profile import PROFILES


def _write_host_profile(dir_: Path) -> str:
    mod = dir_ / "host_fixture_profile.py"
    mod.write_text(
        "from versum.profile import Profile, register\n"
        "from versum.profiles.generic import PROFILE as _G\n"
        "import dataclasses\n"
        "register(dataclasses.replace(_G, id='host-fixture'))\n",
        encoding="utf-8")
    return "host_fixture_profile"


def test_extra_profile_module_registers_host_profile(tmp_path, monkeypatch, capsys):
    modname = _write_host_profile(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(modname, None)
    PROFILES.pop("host-fixture", None)
    # a folder with one plain file to capture
    (tmp_path / "doc.txt").write_text("The controller shall ensure protection.\n", encoding="utf-8")

    assert "host-fixture" not in PROFILES              # not known until the module is imported
    rc = main(["capture", str(tmp_path), "--profile", "host-fixture",
               "--extra-profile-module", modname])
    assert rc == 0
    assert "host-fixture" in PROFILES                  # the seam imported + registered it
