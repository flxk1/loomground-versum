"""Fail when generated state or unexplained scratch artifacts enter version control."""
from __future__ import annotations

import subprocess
from pathlib import Path


FORBIDDEN_PARTS = {".DS_Store", "__pycache__", ".pytest_cache", ".versum"}
FORBIDDEN_NAMES = {"bug.pdf", "ctl.pdf", "junk.py"}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    )
    paths = [Path(raw.decode()) for raw in result.stdout.split(b"\0") if raw]
    failures = []
    for path in paths:
        if path.name in FORBIDDEN_NAMES or FORBIDDEN_PARTS.intersection(path.parts):
            failures.append(path.as_posix())
    if failures:
        print("forbidden tracked artifacts:")
        print("\n".join(f"- {path}" for path in failures))
        return 1
    print(f"hygiene passed: {len(paths)} tracked paths inspected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
