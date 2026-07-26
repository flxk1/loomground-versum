# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flxk1
"""Enforce the writing register: durable artifacts address the maintainer,
not the build session.

This gate scans every tracked ``*.py`` and ``*.md`` file and fails on lines
that carry:

- plan citations (``SOLVER-PLAN``, ``VERSUM-PLAN``, ``RVND-PLAN``)
- the retired ``loomground-ref`` repo name
- wrong repo slugs (``flxk1/solver``, ``flxk1/versum``, bare
  ``github.com/flxk1/loomground``)
- ratification-label citations (``J<n>-ratified``)
- ruling-label citations (``ruling D'`` and similar)
- session references (``this chat``, ``this session``, ``sibling session``)
- an AI co-author trailer (``Co-Authored-By: ... Claude/Anthropic``)
- commit-hash citations (``commit <sha>``)

A maintainer reading a comment, docstring, test, doc, or commit message a
year from now should find the invariant stated in place, not a pointer to
the conversation that produced it.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Directories excluded wholesale: vendored licence text, build/dist
# artifacts.
EXCLUDED_DIR_PREFIXES = ("LICENSES/", "build/", "dist/")

# Path fragments that mark vendored conformance fixtures, which may
# legitimately contain strings that look like violations.
EXCLUDED_PATH_FRAGMENTS = ("/fixtures/", "claim_axes_vectors")

SCANNED_SUFFIXES = (".py", ".md")

PATTERNS = [
    ("plan citation", re.compile(r"\b(SOLVER|VERSUM|RVND)-PLAN\b")),
    ("old repo name", re.compile(r"\bloomground-ref\b")),
    (
        "wrong repo slug",
        re.compile(
            r"flxk1/solver\b|flxk1/versum\b|github\.com/flxk1/loomground(?![-\w])"
        ),
    ),
    ("ratification-label citation", re.compile(r"\bJ\d+-ratified\b")),
    ("ruling-label citation", re.compile(r"\bruling [A-Z][′'´]")),
    ("session reference", re.compile(r"\bthis (chat|session)\b|\bsibling session\b")),
    (
        "AI co-author trailer",
        re.compile(r"Co-Authored-By:\s*.*(Claude|Anthropic)"),
    ),
    ("commit-hash citation", re.compile(r"\bcommit [0-9a-f]{7,40}\b")),
]


def is_excluded(path: Path, self_path: Path) -> bool:
    if path == self_path:
        return True
    posix = path.as_posix()
    if posix.startswith(EXCLUDED_DIR_PREFIXES):
        return True
    if any(fragment in posix for fragment in EXCLUDED_PATH_FRAGMENTS):
        return True
    return False


def scan_file(abs_path: Path, rel_path: Path) -> list[str]:
    hits: list[str] = []
    try:
        text = abs_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return hits
    for lineno, line in enumerate(text.splitlines(), start=1):
        for _name, pattern in PATTERNS:
            match = pattern.search(line)
            if match:
                hits.append(f"{rel_path.as_posix()}:{lineno}:{match.group(0)}")
    return hits


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    self_path = Path(__file__).resolve().relative_to(root)
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    )
    tracked = [Path(raw.decode()) for raw in result.stdout.split(b"\0") if raw]

    failures: list[str] = []
    scanned = 0
    for rel_path in tracked:
        if rel_path.suffix not in SCANNED_SUFFIXES:
            continue
        if is_excluded(rel_path, self_path):
            continue
        scanned += 1
        failures.extend(scan_file(root / rel_path, rel_path))

    if failures:
        print("register-cleanliness violations:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(f"register check passed: {scanned} files scanned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
