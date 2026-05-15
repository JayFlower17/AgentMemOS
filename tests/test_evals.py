import json

from evals.locomo_adapter import load_locomo_samples
from evals.metrics import RetrievalCaseResult, mean_reciprocal_rank, recall_at_k, retrieval_summary
from evals.run_governance_eval import expected_relation_payload, suggestion_matches


def test_locomo_adapter_expands_sessions_and_questions(tmp_path):
    dataset = [
        {
            "sample_id": "sample-1",
            "conversation": {
                "speaker_a": "Mason",
                "speaker_b": "Assistant",
                "session_1_date_time": "2026-05-01 10:00",
                "session_1": [
                    {"speaker": "Mason", "dia_id": "d1", "text": "I prefer bounded retry backoff."},
                    {"speaker": "Assistant", "dia_id": "d2", "text": "I will remember bounded backoff."},
                ],
            },
            "qa": [
                {
                    "question_id": "q1",
                    "question": "What retry policy does Mason prefer?",
                    "answer": "Bounded retry backoff.",
                    "evidence": [{"dia_id": "d1", "text": "I prefer bounded retry backoff."}, "D1:3"],
                }
            ],
        }
    ]
    path = tmp_path / "locomo10.json"
    path.write_text(json.dumps(dataset), encoding="utf-8")

    samples = load_locomo_samples(path)

    assert len(samples) == 1
    sample = samples[0]
    assert sample.task_id == "locomo_sample_1"
    assert len(sample.events) == 2
    assert sample.events[0]["event_type"] == "conversation.turn.observed"
    assert sample.events[0]["agent_role"] == "user"
    assert sample.events[0]["metadata"]["session_timestamp"] == "2026-05-01 10:00"
    assert sample.questions[0].evidence_event_ids == {sample.events[0]["event_id"]}
    assert sample.questions[0].evidence_texts == ["I prefer bounded retry backoff."]


def test_retrieval_metrics_handle_hits_misses_and_empty_evidence():
    cases = [
        RetrievalCaseResult("hit_at_1", ["m1", "m2"], {"m1"}),
        RetrievalCaseResult("hit_at_3", ["m3", "m2", "m4"], {"m4"}),
        RetrievalCaseResult("miss", ["m5"], {"m6"}),
        RetrievalCaseResult("not_evaluable", ["m7"], set()),
    ]

    assert recall_at_k(cases, 1) == 1 / 3
    assert recall_at_k(cases, 3) == 2 / 3
    assert round(mean_reciprocal_rank(cases), 4) == round((1 + 1 / 3) / 3, 4)
    assert retrieval_summary(cases, memory_count=8)["memory_count"] == 8


def test_governance_gold_labels_map_to_expected_memory_ids():
    case = {
        "expected_relation": "supersedes",
        "source_label": "new",
        "target_label": "old",
    }
    label_to_memory = {
        "new": {"memory_id": "mem_new"},
        "old": {"memory_id": "mem_old"},
    }

    expected = expected_relation_payload(case, label_to_memory)

    assert expected == {
        "relation_type": "supersedes",
        "source_memory_id": "mem_new",
        "target_memory_id": "mem_old",
    }
    assert suggestion_matches(
        {
            "relation_type": "supersedes",
            "source_memory_id": "mem_new",
            "target_memory_id": "mem_old",
        },
        expected,
    )
    assert not suggestion_matches(
        {
            "relation_type": "supersedes",
            "source_memory_id": "mem_old",
            "target_memory_id": "mem_new",
        },
        expected,
    )
