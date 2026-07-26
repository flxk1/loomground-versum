#!/usr/bin/env python3
"""Delegate knowledge writes to capture-to-kg's canonical executable.

This adapter intentionally contains no identity, deduplication, or persistence
logic.  It only resolves the installed capture-to-kg script and forwards the
canonical CLI contract unchanged.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

CAPTURE_SCRIPT_ENV = "LOOMGROUND_CAPTURE_TO_KG_SCRIPT"


def _default_capture_script() -> Path:
    # Development checkout seam: <root>/loomground-versum and
    # <root>/editorial/loomground-editorial are sibling products.
    root = Path(__file__).resolve().parents[4]
    return (
        root
        / "editorial"
        / "loomground-editorial"
        / "skills"
        / "capture-to-kg"
        / "scripts"
        / "kg_capture.py"
    )


def resolve_capture_script(explicit: str | None) -> Path:
    candidate = explicit or os.environ.get(CAPTURE_SCRIPT_ENV)
    path = Path(candidate).expanduser() if candidate else _default_capture_script()
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(
            "capture-to-kg executable not found. Install loomground-editorial or set "
            f"{CAPTURE_SCRIPT_ENV} to its skills/capture-to-kg/scripts/kg_capture.py"
        )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Delegate a knowledge write to the canonical capture-to-kg writer.",
        add_help=False,
    )
    parser.add_argument("--capture-script", help=argparse.SUPPRESS)
    known, forwarded = parser.parse_known_args(argv)
    try:
        capture_script = resolve_capture_script(known.capture_script)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    completed = subprocess.run(
        [sys.executable, str(capture_script), *forwarded],
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
