from agentmemos.vector import HashingEmbeddingProvider, InMemoryVectorStore, cosine_similarity, tokenize


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
