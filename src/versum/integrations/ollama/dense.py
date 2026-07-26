"""Device-side Ollama dense embedder for hybrid retrieval (ADR-004).

Implements the ``versum.store.retrieve.Dense`` contract using a LOCAL, model-agnostic embedding model
served by Ollama (e.g. Qwen or Phi on the user's machine). This lives OUTSIDE the engine core:
the core never calls a model; you inject this adapter on the device where the model runs.

    from versum.store.retrieve import from_kg
    from versum.integrations.ollama import OllamaDense
    idx = from_kg(kg_root, dense=OllamaDense(model="qwen2.5:0.5b"))   # or a phi embed model
    idx.search("controllers and processors", filters={"type": "concept"}, k=10)

Requirements on the device: Ollama running locally (default http://localhost:11434) with an
embedding-capable model pulled. No network beyond localhost; deterministic given a fixed model.
Falls back to returning ``None`` (no rerank) if Ollama is unreachable, so search still works on
the deterministic facet+BM25 core.
"""
from __future__ import annotations

import json
import urllib.request

from versum.store.retrieve import Dense


class OllamaDense(Dense):
    def __init__(self, model: str = "qwen2.5:0.5b",
                 endpoint: str = "http://localhost:11434", timeout: float = 30.0):
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def _embed_one(self, text: str):
        body = json.dumps({"model": self.model, "prompt": text}).encode("utf-8")
        req = urllib.request.Request(self.endpoint + "/api/embeddings", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())["embedding"]

    def embed(self, texts):
        """Return a list of vectors, or ``None`` if the model is unreachable (→ no rerank)."""
        try:
            return [self._embed_one(t) for t in texts]
        except Exception:
            return None
