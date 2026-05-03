import math
import json
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Protocol

from sqlalchemy import select

from agentmemos.config import get_settings
from agentmemos.database import SessionLocal
from agentmemos.models import MemoryEmbeddingModel, MemoryRecordModel


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


@dataclass
class OpenAIEmbeddingProvider:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "text-embedding-3-small"
    dimensions: int = 0
    timeout_seconds: float = 20.0
    urlopen: Callable | None = None

    def embed(self, text: str) -> list[float]:
        if not self.api_key:
            raise RuntimeError("OpenAI embedding provider requires an API key.")
        payload: dict[str, object] = {"model": self.model, "input": text}
        if self.dimensions:
            payload["dimensions"] = self.dimensions
        body = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(
            self._endpoint(),
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            opener = self.urlopen or urlrequest.urlopen
            with opener(req, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI embedding request failed with HTTP {exc.code}: {detail}") from exc
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"OpenAI embedding request failed: {exc}") from exc
        try:
            embedding = data["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("OpenAI embedding response did not include data[0].embedding.") from exc
        if not isinstance(embedding, list) or not all(isinstance(value, int | float) for value in embedding):
            raise RuntimeError("OpenAI embedding response returned an invalid embedding vector.")
        return [float(value) for value in embedding]

    def _endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/embeddings"


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


class SqliteVectorStore:
    def __init__(self, *, provider: str = "hashing") -> None:
        self.provider = provider

    def upsert(self, memory_id: str, embedding: list[float]) -> None:
        with SessionLocal() as db:
            record = db.get(MemoryEmbeddingModel, memory_id)
            if record is None:
                record = MemoryEmbeddingModel(memory_id=memory_id)
                db.add(record)
            record.provider = self.provider
            record.dimensions = len(embedding)
            record.embedding = embedding
            db.commit()

    def search(
        self,
        query_embedding: list[float],
        *,
        candidate_ids: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, float]:
        with SessionLocal() as db:
            stmt = select(MemoryEmbeddingModel)
            if candidate_ids is not None:
                stmt = stmt.where(MemoryEmbeddingModel.memory_id.in_(candidate_ids))
            records = list(db.scalars(stmt))
        scores = {
            record.memory_id: cosine_similarity(query_embedding, list(record.embedding or []))
            for record in records
        }
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return dict(ranked[:limit])


def _quote_identifier(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum() or not identifier[0].isalpha():
        raise ValueError(f"Unsafe SQL identifier: {identifier}")
    return f'"{identifier}"'


def _to_pgvector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{value:.12g}" for value in embedding) + "]"


class PgVectorStore:
    def __init__(
        self,
        *,
        database_url: str,
        table_name: str = "memory_embeddings",
        dimensions: int = 64,
        provider: str = "hashing",
        auto_setup: bool = True,
        connection_factory=None,
    ) -> None:
        self.database_url = database_url
        self.table_name = table_name
        self.dimensions = dimensions
        self.provider = provider
        self.connection_factory = connection_factory or self._default_connection_factory
        self.table_sql = _quote_identifier(table_name)
        if auto_setup:
            self.setup()

    def setup(self) -> None:
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.table_sql} (
                        memory_id TEXT PRIMARY KEY,
                        provider TEXT NOT NULL,
                        dimensions INTEGER NOT NULL,
                        embedding vector({self.dimensions}) NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self.table_name}_embedding_hnsw_idx
                    ON {self.table_sql}
                    USING hnsw (embedding vector_cosine_ops)
                    """
                )
            conn.commit()

    def upsert(self, memory_id: str, embedding: list[float]) -> None:
        if len(embedding) != self.dimensions:
            raise ValueError(f"Expected embedding with {self.dimensions} dimensions, got {len(embedding)}")
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {self.table_sql} (memory_id, provider, dimensions, embedding, updated_at)
                    VALUES (%s, %s, %s, %s::vector, now())
                    ON CONFLICT (memory_id)
                    DO UPDATE SET
                        provider = EXCLUDED.provider,
                        dimensions = EXCLUDED.dimensions,
                        embedding = EXCLUDED.embedding,
                        updated_at = now()
                    """,
                    (memory_id, self.provider, len(embedding), _to_pgvector_literal(embedding)),
                )
            conn.commit()

    def search(
        self,
        query_embedding: list[float],
        *,
        candidate_ids: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, float]:
        if len(query_embedding) != self.dimensions:
            raise ValueError(f"Expected query embedding with {self.dimensions} dimensions, got {len(query_embedding)}")
        query_literal = _to_pgvector_literal(query_embedding)
        params: list[object] = [query_literal]
        where_clause = ""
        if candidate_ids is not None:
            if not candidate_ids:
                return {}
            where_clause = "WHERE memory_id = ANY(%s)"
            params.append(candidate_ids)
        params.extend([query_literal, limit])
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT memory_id, 1 - (embedding <=> %s::vector) AS score
                    FROM {self.table_sql}
                    {where_clause}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    params,
                )
                rows = cur.fetchall()
        return {memory_id: float(score) for memory_id, score in rows}

    def _default_connection_factory(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PgVectorStore requires installing the optional 'postgres' dependency.") from exc
        return psycopg.connect(self.database_url)


def create_vector_store(*, backend: str = "memory") -> VectorStore:
    if backend == "memory":
        return InMemoryVectorStore()
    if backend == "sqlite":
        settings = get_settings()
        return SqliteVectorStore(provider=settings.embedding_provider)
    if backend == "pgvector":
        settings = get_settings()
        return PgVectorStore(
            database_url=settings.pgvector_url,
            table_name=settings.pgvector_table_name,
            dimensions=settings.pgvector_dimensions,
            provider=settings.embedding_provider,
        )
    raise ValueError(f"Unsupported vector store backend: {backend}")


def create_embedding_provider(*, provider: str = "hashing") -> EmbeddingProvider:
    settings = get_settings()
    if provider == "hashing":
        return HashingEmbeddingProvider(dimensions=settings.pgvector_dimensions)
    if provider == "openai":
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_embedding_api_key,
            base_url=settings.openai_embedding_base_url,
            model=settings.openai_embedding_model,
            dimensions=settings.openai_embedding_dimensions,
            timeout_seconds=settings.openai_embedding_timeout_seconds,
        )
    raise ValueError(f"Unsupported embedding provider: {provider}")


def memory_embedding_text(memory: MemoryRecordModel) -> str:
    return f"{memory.summary}\n{memory.content}"
