"""The engine never touches the network. Binaries arrive out-of-band only.

This turns the "no in-session fetch" policy into an executable guard: it scans the engine
source for network primitives and fails if any appear. `urllib.parse` is allowed — it is
string handling (URL unquoting), not I/O. `integrations/` is excluded on purpose: its
Ollama adapters make real local HTTP calls to a device-side model server when a caller
wires one in directly; no shipped skill does this by default. See the "Local-first and
model-agnostic" section of the README.
"""
from pathlib import Path

VERSUM = Path(__file__).resolve().parent.parent / "src" / "versum"

FORBIDDEN = [
    "urllib.request", "urlopen", "import requests", "from requests",
    "http.client", "httpx", "aiohttp", "socket.socket", "subprocess",
    "wget", "curl ",
]


def test_engine_has_no_network_primitives():
    for f in sorted(VERSUM.rglob("*.py")):
        if "integrations" in f.relative_to(VERSUM).parts:
            continue
        src = f.read_text(encoding="utf-8")
        for tok in FORBIDDEN:
            assert tok not in src, (
                f"{f.relative_to(VERSUM.parent)} uses network/shell primitive {tok!r} "
                f"— the engine must never fetch binaries in-session")
