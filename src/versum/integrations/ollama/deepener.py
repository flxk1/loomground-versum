"""Device-side Ollama LLM deepener (ADR-005).

Implements ``versum.deepen.Deepener`` with a LOCAL, model-agnostic model served by Ollama
(Qwen / Phi). Lives OUTSIDE the engine core: the core never calls a model; inject this on the
device. Returns a richer structure than the deterministic coordinate — relations, sub-claims, a
proposed mental-model label — as validated JSON.

    from versum.deepen import deepen
    from versum.integrations.ollama import OllamaDeepener
    records = deepen(claims, deepener=OllamaDeepener(model="qwen2.5:3b"),
                     canon=canon_result, budget=200, out_path=f"{kg_root}/deepenings.jsonl")

Requirements: Ollama running locally with a capable instruct model pulled. Deterministic only
insofar as the model is (set the model's temperature to 0 on the device for reproducibility).
On any error or unparseable output it returns ``{}`` (no deepening), so the harness degrades
gracefully to the deterministic layer.
"""
from __future__ import annotations

import json
import urllib.request

from versum.deepen import Deepener

_SCHEMA_HINT = (
    "Return ONLY compact JSON with keys: "
    '"relations" (list of {subject, relation, object}), '
    '"sub_claims" (list of short strings), '
    '"mental_model" ({label, summary}). No prose, no code fences.')


class OllamaDeepener(Deepener):
    def __init__(self, model: str = "qwen2.5:3b",
                 endpoint: str = "http://localhost:11434", timeout: float = 60.0):
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def deepen(self, text: str, context: dict) -> dict:
        prompt = (f"{_SCHEMA_HINT}\n\nClaim (predicate={context.get('predicate','')}, "
                  f"domain={context.get('domain','')}):\n{text}\n\nJSON:")
        body = json.dumps({"model": self.model, "prompt": prompt, "stream": False,
                           "format": "json", "options": {"temperature": 0}}).encode("utf-8")
        try:
            req = urllib.request.Request(self.endpoint + "/api/generate", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read())["response"]
            return json.loads(raw)
        except Exception:
            return {}
