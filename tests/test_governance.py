import asyncio
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from agentmemos.database import SessionLocal
from agentmemos.main import app
from agentmemos.config import Settings
from agentmemos.governance import OpenAIGovernanceReviewer, jaccard, list_relation_suggestions, memory_terms
from agentmemos.jobs import GovernanceScheduler
from agentmemos.models import MemoryRecordModel, MemoryRelationModel


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


def test_openai_governance_reviewer_generates_suggestion_without_mutating_relations():
    with TestClient(app) as client:
        task_id = f"task_llm_governance_{uuid4().hex}"
        first = client.post(
            "/memories",
            json={
                "task_id": task_id,
                "agent_id": "reviewer_1",
                "memory_type": "episodic",
                "scope": "team-shared",
                "content": "Redis queue should decouple memory extraction from API writes.",
            },
        ).json()
        second = client.post(
            "/memories",
            json={
                "task_id": task_id,
                "agent_id": "reviewer_2",
                "memory_type": "episodic",
                "scope": "team-shared",
                "content": "Redis queue keeps extraction jobs outside the request path.",
            },
        ).json()

        def fake_transport(payload):
            assert payload["model"] == "governance-test-model"
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "relation_type": "duplicates",
                                    "confidence": 0.91,
                                    "source_memory_id": first["memory_id"],
                                    "target_memory_id": second["memory_id"],
                                    "reason": "Both memories describe Redis queue decoupling extraction from API requests.",
                                    "evidence": {"shared_concept": "redis queue decoupling"},
                                    "suggested_action": "Review and keep one canonical Redis queue guidance memory.",
                                }
                            )
                        }
                    }
                ]
            }

        reviewer = OpenAIGovernanceReviewer(
            model="governance-test-model",
            min_confidence=0.7,
            transport=fake_transport,
        )
        with SessionLocal() as db:
            left = db.get(MemoryRecordModel, first["memory_id"])
            right = db.get(MemoryRecordModel, second["memory_id"])
            suggestion = reviewer.suggest(db, left, right)
            relation = db.scalar(
                select(MemoryRelationModel).where(
                    MemoryRelationModel.source_memory_id == first["memory_id"],
                    MemoryRelationModel.target_memory_id == second["memory_id"],
                )
            )

        assert suggestion is not None
        assert suggestion.relation_type == "duplicates"
        assert suggestion.confidence == 0.91
        assert suggestion.evidence["provider"] == "openai"
        assert relation is None


def test_list_relation_suggestions_can_include_injected_llm_reviewer_suggestion():
    with TestClient(app) as client:
        task_id = f"task_llm_suggestion_list_{uuid4().hex}"
        first = client.post(
            "/memories",
            json={
                "task_id": task_id,
                "agent_id": "coder_1",
                "memory_type": "episodic",
                "scope": "task-local",
                "content": "Redis queue should run memory extraction outside API requests.",
            },
        ).json()
        second = client.post(
            "/memories",
            json={
                "task_id": task_id,
                "agent_id": "coder_2",
                "memory_type": "episodic",
                "scope": "task-local",
                "content": "Redis queue should run embedding indexing after event ingestion.",
            },
        ).json()

        def fake_transport(_payload):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "relation_type": "supersedes",
                                    "confidence": 0.88,
                                    "source_memory_id": second["memory_id"],
                                    "target_memory_id": first["memory_id"],
                                    "reason": "The second memory gives a more specific follow-up job pipeline.",
                                    "evidence": {"newer_guidance": "embedding indexing after event ingestion"},
                                    "suggested_action": "Ask a reviewer whether the newer memory should supersede the older one.",
                                }
                            )
                        }
                    }
                ]
            }

        reviewer = OpenAIGovernanceReviewer(min_confidence=0.7, transport=fake_transport)
        with SessionLocal() as db:
            suggestions = list_relation_suggestions(db, task_id=task_id, reviewer_provider=reviewer, limit=10)

        matching = [item for item in suggestions if item.relation_type == "supersedes"]
        assert matching
        assert matching[0].source_memory_id == second["memory_id"]
        assert matching[0].target_memory_id == first["memory_id"]
        assert matching[0].evidence["reviewer"] == "openai-compatible-governance-reviewer-v1"


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
