from agentmemos.database import init_db
from agentmemos.vector import (
    HashingEmbeddingProvider,
    InMemoryVectorStore,
    SqliteVectorStore,
    PgVectorStore,
    cosine_similarity,
    create_vector_store,
    tokenize,
)


def test_hashing_embedding_provider_scores_related_text_higher_than_unrelated_text():
    provider = HashingEmbeddingProvider(dimensions=128)

    query = provider.embed("bounded retry backoff approval")
    related = provider.embed("retry policy requires bounded backoff before approval")
    unrelated = provider.embed("dashboard color palette and layout spacing")

    assert cosine_similarity(query, related) > cosine_similarity(query, unrelated)


def test_in_memory_vector_store_filters_candidates_and_ranks_results():
    provider = HashingEmbeddingProvider(dimensions=128)
    store = InMemoryVectorStore()
    store.upsert("mem_retry", provider.embed("retry policy bounded backoff approval"))
    store.upsert("mem_layout", provider.embed("dashboard layout spacing typography"))

    scores = store.search(
        provider.embed("bounded backoff retry"),
        candidate_ids=["mem_retry"],
        limit=10,
    )

    assert list(scores) == ["mem_retry"]
    assert scores["mem_retry"] > 0


def test_tokenize_keeps_stable_memory_terms():
    assert tokenize("Retry-policy requires bounded backoff.") == [
        "retry-policy",
        "requires",
        "bounded",
        "backoff",
    ]


def test_sqlite_vector_store_persists_embeddings_across_instances():
    init_db()
    provider = HashingEmbeddingProvider(dimensions=128)
    first_store = SqliteVectorStore()
    first_store.upsert("mem_sqlite_vector_test", provider.embed("retry bounded backoff approval"))

    second_store = SqliteVectorStore()
    scores = second_store.search(
        provider.embed("bounded retry backoff"),
        candidate_ids=["mem_sqlite_vector_test"],
    )

    assert "mem_sqlite_vector_test" in scores
    assert scores["mem_sqlite_vector_test"] > 0


def test_create_vector_store_defaults_to_memory_and_supports_sqlite():
    assert isinstance(create_vector_store(), InMemoryVectorStore)
    assert isinstance(create_vector_store(backend="sqlite"), SqliteVectorStore)


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows=None):
        self.cursor_instance = FakeCursor(rows=rows)
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1


def test_pgvector_store_setup_and_upsert_use_vector_extension_and_conflict_update():
    connection = FakeConnection()
    store = PgVectorStore(
        database_url="postgresql://example/agentmemos",
        dimensions=3,
        auto_setup=True,
        connection_factory=lambda: connection,
    )

    store.upsert("mem_pg", [0.1, 0.2, 0.3])
    sql_text = "\n".join(call[0] for call in connection.cursor_instance.calls)

    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql_text
    assert "CREATE TABLE IF NOT EXISTS" in sql_text
    assert "USING hnsw" in sql_text
    assert "ON CONFLICT (memory_id)" in sql_text
    assert connection.cursor_instance.calls[-1][1][0] == "mem_pg"
    assert connection.cursor_instance.calls[-1][1][3] == "[0.1,0.2,0.3]"
    assert connection.commits == 2


def test_pgvector_store_search_uses_cosine_distance_and_candidate_filter():
    connection = FakeConnection(rows=[("mem_retry", 0.91), ("mem_backoff", 0.82)])
    store = PgVectorStore(
        database_url="postgresql://example/agentmemos",
        dimensions=3,
        auto_setup=False,
        connection_factory=lambda: connection,
    )

    scores = store.search([0.1, 0.2, 0.3], candidate_ids=["mem_retry", "mem_backoff"], limit=2)

    sql, params = connection.cursor_instance.calls[-1]
    assert "embedding <=>" in sql
    assert "memory_id = ANY" in sql
    assert params == ["[0.1,0.2,0.3]", ["mem_retry", "mem_backoff"], "[0.1,0.2,0.3]", 2]
    assert scores == {"mem_retry": 0.91, "mem_backoff": 0.82}


def test_pgvector_store_validates_dimensions():
    store = PgVectorStore(
        database_url="postgresql://example/agentmemos",
        dimensions=3,
        auto_setup=False,
        connection_factory=lambda: FakeConnection(),
    )

    try:
        store.upsert("mem_bad", [0.1, 0.2])
    except ValueError as exc:
        assert "Expected embedding with 3 dimensions" in str(exc)
    else:
        raise AssertionError("Expected dimension validation error")
