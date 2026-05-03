import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from agentmemos.main import app
from agentmemos.config import Settings
from agentmemos.governance import jaccard, memory_terms
from agentmemos.jobs import GovernanceScheduler
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


def test_governance_scheduler_run_once_accepts_duplicate_suggestions():
    with TestClient(app) as client:
        task_id = f"task_governance_scheduler_{uuid4().hex}"
        payload = {
            "task_id": task_id,
            "agent_id": "reviewer_1",
            "memory_type": "episodic",
            "scope": "team-shared",
            "content": "Retry policy requires bounded backoff limits before approval.",
        }
        client.post("/memories", json=payload)
        client.post(
            "/memories",
            json={
                **payload,
                "agent_id": "reviewer_2",
                "content": "Retry policy requires bounded backoff limits before approval and release.",
            },
        )

        scheduler = GovernanceScheduler(
            Settings(
                governance_scheduler_enabled=True,
                governance_scheduler_interval_seconds=60,
                governance_scheduler_actor="test_scheduler",
                governance_duplicate_confidence_threshold=0.85,
                governance_max_accepts=1,
            )
        )
        asyncio.run(scheduler.run_once())

        state = scheduler.state()
        assert state["enabled"] is True
        assert state["last_error"] is None
        assert state["last_summary"]["accepted_suggestions"] == 1
        assert state["last_summary"]["action"]["action_type"] == "governance_pass"


def test_governance_scheduler_status_endpoint_reports_default_disabled_state():
    with TestClient(app) as client:
        response = client.get("/governance/scheduler")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["running"] is True
    assert body["last_summary"] is None
