from agentmemos.database import init_db
from agentmemos.vector import (
    HashingEmbeddingProvider,
    InMemoryVectorStore,
    SqliteVectorStore,
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
