"""Smoke test for OpenAI-compatible embedding providers.

The script never prints API keys. For local development it can infer a labeled
Embedding key from ~/Desktop/LLM-API-KEY.txt when explicit environment
variables are not set.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentmemos.config import get_settings
from agentmemos.vector import OpenAIEmbeddingProvider, create_embedding_provider


def configure_local_defaults() -> None:
    key_file = Path.home() / "Desktop" / "LLM-API-KEY.txt"
    if not key_file.exists():
        return
    os.environ.setdefault("AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_FILE", str(key_file))
    os.environ.setdefault("AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_LABEL", "Embedding")
    os.environ.setdefault("AGENTMEMOS_OPENAI_EMBEDDING_BASE_URL", "https://api.jiekou.ai/openai")
    os.environ.setdefault("AGENTMEMOS_OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")


def main() -> None:
    configure_local_defaults()
    get_settings.cache_clear()
    provider = create_embedding_provider(provider="openai")
    if not isinstance(provider, OpenAIEmbeddingProvider):
        raise RuntimeError("Expected OpenAIEmbeddingProvider.")
    embedding = provider.embed("AgentMemOS indexes memory with semantic embeddings.")
    if not embedding:
        raise RuntimeError("Embedding provider returned an empty vector.")
    print("OpenAI-compatible embedding smoke passed.")
    print(f"Base URL: {provider.base_url}")
    print(f"Model: {provider.model}")
    print(f"Dimensions returned: {len(embedding)}")


if __name__ == "__main__":
    main()
