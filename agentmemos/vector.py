import math
from collections import Counter
from typing import Protocol

from agentmemos.models import MemoryRecordModel


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


class VectorStore(Protocol):
    def upsert(self, memory_id: str, embedding: list[float]) -> None: ...

    def search(
        self,
        query_embedding: list[float],
        *,
        candidate_ids: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, float]: ...


def tokenize(text: str) -> list[str]:
    tokens = []
    for raw in text.casefold().replace(".", " ").replace(",", " ").split():
        token = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_"})
        if len(token) > 2:
            tokens.append(token)
    return tokens


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


class HashingEmbeddingProvider:
    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0 for _ in range(self.dimensions)]
        counts = Counter(tokenize(text))
        for token, count in counts.items():
            vector[hash(token) % self.dimensions] += float(count)
        norm = math.sqrt(sum(value * value for value in vector))
        if not norm:
            return vector
        return [value / norm for value in vector]


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._embeddings: dict[str, list[float]] = {}

    def upsert(self, memory_id: str, embedding: list[float]) -> None:
        self._embeddings[memory_id] = embedding

    def search(
        self,
        query_embedding: list[float],
        *,
        candidate_ids: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, float]:
        allowed = set(candidate_ids) if candidate_ids is not None else None
        scores = {
            memory_id: cosine_similarity(query_embedding, embedding)
            for memory_id, embedding in self._embeddings.items()
            if allowed is None or memory_id in allowed
        }
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return dict(ranked[:limit])


def memory_embedding_text(memory: MemoryRecordModel) -> str:
    return f"{memory.summary}\n{memory.content}"
