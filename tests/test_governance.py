from agentmemos.governance import jaccard, memory_terms
from agentmemos.models import MemoryRecordModel


def test_memory_terms_removes_common_words_and_normalizes_tokens():
    memory = MemoryRecordModel(
        task_id="task_unit",
        agent_id="reviewer_1",
        memory_type="episodic",
        scope="team-shared",
        summary="The reviewer should check bounded backoff.",
        content="Reviewer found that retry-policy requires bounded backoff before approval.",
    )

    terms = memory_terms(memory)

    assert "reviewer" not in terms
    assert "should" not in terms
    assert "bounded" in terms
    assert "backoff" in terms
    assert "retry-policy" in terms


def test_jaccard_scores_overlap_between_term_sets():
    assert jaccard({"retry", "backoff"}, {"retry", "backoff"}) == 1.0
    assert jaccard({"retry"}, {"backoff"}) == 0.0
    assert jaccard({"retry", "backoff"}, {"retry", "timeout"}) == 1 / 3
