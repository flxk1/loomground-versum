"""Optional adapters for local Ollama-compatible services."""

from .deepener import OllamaDeepener
from .dense import OllamaDense

__all__ = ["OllamaDeepener", "OllamaDense"]
