from uuid import uuid4
import pytest

from fastapi.testclient import TestClient

from agentmemos.main import app
from agentmemos.retrieval import _score_memory
from agentmemos.schemas import RetrieveRequest


def test_event_to_retrieval_trace_flow():
    with TestClient(app) as client:
        task_id = f"task_test_flow_{uuid4().hex}"
        event_response = client.post(
            "/events",
            json={
                "event_type": "review.finding.created",
                "task_id": task_id,
                "agent_id": "reviewer_1",
                "agent_role": "reviewer",
                "content": "The reviewer found that retries need bounded backoff before approval.",
            },
        )
        assert event_response.status_code == 202
        client.app.state.memory_worker._process_event(event_response.json()["event_id"])

        retrieve_response = client.post(
            "/retrieve",
            json={
                "task_id": task_id,
                "agent_id": "coder_1",
                "agent_role": "coder",
                "query": "bounded backoff approval risk",
                "allowed_scopes": ["task-local", "team-shared", "project-global"],
            },
        )

        assert retrieve_response.status_code == 200
        body = retrieve_response.json()
        assert body["memories"]
        assert "bounded backoff" in body["packed_context"]

        trace_response = client.get(f"/traces/{body['trace_id']}")
        assert trace_response.status_code == 200
        trace = trace_response.json()
        assert trace["selected_memories"]
        assert trace["scored_memories"]
        assert trace["scored_memories"][0]["selected"] is True
        assert "score_parts" in trace["scored_memories"][0]

        source_event_id = event_response.json()["event_id"]
        task_memories = client.get(f"/memories?task_id={task_id}&limit=200").json()
        extracted_memory = next(memory for memory in task_memories if memory["source_event_id"] == source_event_id)
        memory_id = extracted_memory["memory_id"]
        decisions_response = client.get(f"/memories/{memory_id}/decisions")
        assert decisions_response.status_code == 200
        decisions = decisions_response.json()
        extracted_decision = next(decision for decision in decisions if decision["decision_type"] == "extracted")
        assert extracted_decision["source_event_id"] == source_event_id
        assert extracted_decision["chosen_scope"] == "team-shared"
        assert "Review findings" in extracted_decision["reason"]


def test_agent_local_memory_is_hidden_from_other_agents():
    with TestClient(app) as client:
        memory_response = client.post(
            "/memories",
            json={
                "task_id": "task_scope_test",
                "agent_id": "coder_1",
                "memory_type": "episodic",
                "scope": "agent-local",
                "content": "Coder local scratch should not be visible to reviewer.",
            },
        )
        assert memory_response.status_code == 201

        retrieve_response = client.post(
            "/retrieve",
            json={
                "task_id": "task_scope_test",
                "agent_id": "reviewer_1",
                "agent_role": "reviewer",
                "query": "local scratch",
                "allowed_scopes": ["agent-local", "task-local", "team-shared"],
            },
        )

        body = retrieve_response.json()
        assert body["memories"] == []
        trace = client.get(f"/traces/{body['trace_id']}").json()
        memory_id = memory_response.json()["memory_id"]
        assert memory_id in trace["filtered_memories"]
        assert trace["filter_reasons"][memory_id] == "Filtered another agent's local memory."


def test_duplicate_memory_writes_are_deduplicated_and_audited():
    with TestClient(app) as client:
        task_id = f"task_dedup_test_{uuid4().hex}"
        payload = {
            "task_id": task_id,
            "agent_id": "coder_1",
            "memory_type": "episodic",
            "scope": "task-local",
            "content": "Retry policy should keep bounded backoff before approval.",
        }
        first_response = client.post("/memories", json=payload)
        second_response = client.post(
            "/memories",
            json={**payload, "content": "  retry policy should keep bounded   backoff before approval.  "},
        )

        assert first_response.status_code == 201
        assert second_response.status_code == 201
        assert second_response.json()["memory_id"] == first_response.json()["memory_id"]

        memory_id = first_response.json()["memory_id"]
        decisions_response = client.get(f"/memories/{memory_id}/decisions")
        assert decisions_response.status_code == 200
        decisions = decisions_response.json()
        decision_types = {decision["decision_type"] for decision in decisions}
        assert {"manual", "deduplicated"}.issubset(decision_types)
        deduplicated = next(decision for decision in decisions if decision["decision_type"] == "deduplicated")
        assert "Duplicate memory content" in deduplicated["reason"]
        assert deduplicated["signals"]["dedup_strategy"] == "exact-normalized-content"


def test_dashboard_routes_are_available():
    with TestClient(app) as client:
        page_response = client.get("/")
        assert page_response.status_code == 200
        assert "AgentMemOS" in page_response.text
        assert "Trace explain" in page_response.text
        assert "Trace explain panel" in page_response.text
        assert "Decision details" in page_response.text
        assert "manual" in page_response.text
        assert "extracted" in page_response.text
        assert "deduplicated" in page_response.text

        stats_response = client.get("/dashboard/stats")
        assert stats_response.status_code == 200
        assert "total_memories" in stats_response.json()
        assert "status_counts" in stats_response.json()
        assert "total_promotions" in stats_response.json()

        memories_response = client.get("/memories")
        assert memories_response.status_code == 200
        assert isinstance(memories_response.json(), list)

        decisions_response = client.get("/memory-decisions")
        assert decisions_response.status_code == 200
        assert isinstance(decisions_response.json(), list)


def test_memory_detail_and_promotion_history():
    with TestClient(app) as client:
        memory_response = client.post(
            "/memories",
            json={
                "task_id": "task_promotion_test",
                "agent_id": "reviewer_1",
                "memory_type": "episodic",
                "scope": "task-local",
                "content": "Reviewer confirmed a retry backoff risk.",
            },
        )
        assert memory_response.status_code == 201
        memory_id = memory_response.json()["memory_id"]

        detail_response = client.get(f"/memories/{memory_id}")
        assert detail_response.status_code == 200
        assert detail_response.json()["memory_id"] == memory_id

        promote_response = client.post(
            f"/memories/{memory_id}/promote",
            json={"to_scope": "team-shared", "reason": "Reviewer finding is useful to the team."},
        )
        assert promote_response.status_code == 200
        assert promote_response.json()["scope"] == "team-shared"

        history_response = client.get(f"/memories/{memory_id}/promotions")
        assert history_response.status_code == 200
        history = history_response.json()
        assert len(history) == 1
        assert history[0]["from_scope"] == "task-local"
        assert history[0]["to_scope"] == "team-shared"


def test_memory_status_history_is_auditable():
    with TestClient(app) as client:
        memory_response = client.post(
            "/memories",
            json={
                "task_id": "task_status_test",
                "agent_id": "reviewer_1",
                "memory_type": "episodic",
                "scope": "task-local",
                "content": "This memory should be archived after the review closes.",
            },
        )
        assert memory_response.status_code == 201
        memory_id = memory_response.json()["memory_id"]

        status_response = client.post(
            f"/memories/{memory_id}/status",
            json={"status": "archived", "reason": "Review finding is no longer active."},
        )
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "archived"

        history_response = client.get(f"/memories/{memory_id}/status-decisions")
        assert history_response.status_code == 200
        history = history_response.json()
        assert len(history) == 1
        assert history[0]["memory_id"] == memory_id
        assert history[0]["from_status"] == "active"
        assert history[0]["to_status"] == "archived"


def test_memory_relation_can_supersede_old_memory():
    with TestClient(app) as client:
        task_id = f"task_relation_test_{uuid4().hex}"
        old_response = client.post(
            "/memories",
            json={
                "task_id": task_id,
                "agent_id": "reviewer_1",
                "memory_type": "episodic",
                "scope": "team-shared",
                "content": "Reviewer initially allowed unbounded retries.",
            },
        )
        new_response = client.post(
            "/memories",
            json={
                "task_id": task_id,
                "agent_id": "reviewer_1",
                "memory_type": "episodic",
                "scope": "team-shared",
                "content": "Reviewer requires bounded backoff before retry approval.",
            },
        )
        old_memory_id = old_response.json()["memory_id"]
        new_memory_id = new_response.json()["memory_id"]

        relation_response = client.post(
            "/memory-relations",
            json={
                "source_memory_id": new_memory_id,
                "target_memory_id": old_memory_id,
                "relation_type": "supersedes",
                "reason": "The later review decision replaces the initial retry guidance.",
            },
        )

        assert relation_response.status_code == 201
        relation = relation_response.json()
        assert relation["relation_type"] == "supersedes"
        assert relation["status"] == "open"

        old_detail = client.get(f"/memories/{old_memory_id}").json()
        assert old_detail["status"] == "superseded"

        relation_list = client.get(f"/memories/{old_memory_id}/relations").json()
        assert relation["relation_id"] in {item["relation_id"] for item in relation_list}

        status_history = client.get(f"/memories/{old_memory_id}/status-decisions").json()
        assert status_history[0]["to_status"] == "superseded"

        retrieve_response = client.post(
            "/retrieve",
            json={
                "task_id": task_id,
                "agent_id": "coder_1",
                "agent_role": "coder",
                "query": "retry approval bounded",
                "allowed_scopes": ["team-shared"],
            },
        )
        body = retrieve_response.json()
        returned_ids = {memory["memory_id"] for memory in body["memories"]}
        assert new_memory_id in returned_ids
        assert old_memory_id not in returned_ids
        trace = client.get(f"/traces/{body['trace_id']}").json()
        assert old_memory_id in trace["filtered_memories"]
        assert "superseded" in trace["filter_reasons"][old_memory_id]
        new_scored = next(item for item in trace["scored_memories"] if item["memory_id"] == new_memory_id)
        assert new_scored["governance"][0]["relation_type"] == "supersedes"

        resolve_response = client.post(
            f"/memory-relations/{relation['relation_id']}/resolve",
            json={"reason": "Reviewer accepted the newer guidance."},
        )
        assert resolve_response.status_code == 200
        assert resolve_response.json()["status"] == "resolved"


def test_memory_insights_surface_agent_action_items():
    with TestClient(app) as client:
        task_id = f"task_insight_test_{uuid4().hex}"
        first_response = client.post(
            "/memories",
            json={
                "task_id": task_id,
                "agent_id": "reviewer_1",
                "memory_type": "episodic",
                "scope": "team-shared",
                "content": "Reviewer says retries are safe without additional limits.",
            },
        )
        second_response = client.post(
            "/memories",
            json={
                "task_id": task_id,
                "agent_id": "reviewer_2",
                "memory_type": "episodic",
                "scope": "team-shared",
                "content": "Reviewer says retries require bounded backoff limits.",
            },
        )
        relation_response = client.post(
            "/memory-relations",
            json={
                "source_memory_id": first_response.json()["memory_id"],
                "target_memory_id": second_response.json()["memory_id"],
                "relation_type": "conflicts_with",
                "reason": "Reviewers disagree about retry safety.",
            },
        )
        assert relation_response.status_code == 201

        retrieve_response = client.post(
            "/retrieve",
            json={
                "task_id": task_id,
                "agent_id": "coder_1",
                "agent_role": "coder",
                "query": "unrelated deployment window",
                "allowed_scopes": ["agent-local"],
            },
        )
        assert retrieve_response.status_code == 200
        assert retrieve_response.json()["memories"] == []

        insights_response = client.get(f"/memory-insights?task_id={task_id}")
        assert insights_response.status_code == 200
        insight_types = {insight["insight_type"] for insight in insights_response.json()}
        assert "open_conflicts_with" in insight_types
        assert "retrieval_miss" in insight_types


def test_memory_relation_suggestions_find_duplicates_and_conflicts():
    with TestClient(app) as client:
        duplicate_task_id = f"task_suggestion_duplicate_{uuid4().hex}"
        conflict_task_id = f"task_suggestion_conflict_{uuid4().hex}"
        duplicate_payload = {
            "task_id": duplicate_task_id,
            "agent_id": "reviewer_1",
            "memory_type": "episodic",
            "scope": "team-shared",
            "content": "Retry policy requires bounded backoff limits before approval.",
        }
        first_duplicate = client.post("/memories", json=duplicate_payload)
        second_duplicate = client.post(
            "/memories",
            json={
                **duplicate_payload,
                "agent_id": "reviewer_2",
                "content": "Retry policy requires bounded backoff limits before approval and release.",
            },
        )
        assert first_duplicate.status_code == 201
        assert second_duplicate.status_code == 201

        duplicate_suggestions = client.get(f"/memory-relation-suggestions?task_id={duplicate_task_id}").json()
        assert any(suggestion["relation_type"] == "duplicates" for suggestion in duplicate_suggestions)

        first_conflict = client.post(
            "/memories",
            json={
                "task_id": conflict_task_id,
                "agent_id": "reviewer_1",
                "memory_type": "episodic",
                "scope": "team-shared",
                "content": "Reviewer says retries are safe without additional limits.",
            },
        )
        second_conflict = client.post(
            "/memories",
            json={
                "task_id": conflict_task_id,
                "agent_id": "reviewer_2",
                "memory_type": "episodic",
                "scope": "team-shared",
                "content": "Reviewer says retries require bounded backoff limits.",
            },
        )
        assert first_conflict.status_code == 201
        assert second_conflict.status_code == 201

        conflict_suggestions = client.get(f"/memory-relation-suggestions?task_id={conflict_task_id}").json()
        assert any(suggestion["relation_type"] == "conflicts_with" for suggestion in conflict_suggestions)


def test_memory_relation_suggestion_can_be_accepted_with_audit_action():
    with TestClient(app) as client:
        task_id = f"task_suggestion_accept_{uuid4().hex}"
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

        suggestions = client.get(f"/memory-relation-suggestions?task_id={task_id}").json()
        suggestion = next(item for item in suggestions if item["relation_type"] == "duplicates")
        accept_response = client.post(
            f"/memory-relation-suggestions/{suggestion['suggestion_id']}/accept",
            json={"actor": "governance_agent", "reason": "Accept duplicate suggestion for canonical cleanup."},
        )
        assert accept_response.status_code == 200
        accepted = accept_response.json()
        assert accepted["relation"]["relation_type"] == "duplicates"
        assert accepted["action"]["actor"] == "governance_agent"
        assert accepted["action"]["suggestion_id"] == suggestion["suggestion_id"]

        relation_ids = {item["relation_id"] for item in client.get("/memory-relations").json()}
        assert accepted["relation"]["relation_id"] in relation_ids

        actions = client.get("/memory-governance-actions").json()
        assert accepted["action"]["action_id"] in {item["action_id"] for item in actions}

        remaining = client.get(f"/memory-relation-suggestions?task_id={task_id}").json()
        assert suggestion["suggestion_id"] not in {item["suggestion_id"] for item in remaining}


def test_governance_run_accepts_duplicate_suggestions_and_records_summary():
    with TestClient(app) as client:
        task_id = f"task_governance_run_{uuid4().hex}"
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
        before = client.get(f"/memory-relation-suggestions?task_id={task_id}").json()
        assert any(suggestion["relation_type"] == "duplicates" for suggestion in before)

        run_response = client.post(
            "/governance/run",
            json={"actor": "governance_agent", "duplicate_confidence_threshold": 0.85, "max_accepts": 1},
        )
        assert run_response.status_code == 200
        summary = run_response.json()
        assert summary["accepted_suggestions"] == 1
        assert len(summary["accepted_relation_ids"]) == 1
        assert summary["action"]["action_type"] == "governance_pass"
        assert summary["action"]["evidence"]["max_accepts"] == 1

        actions = client.get("/memory-governance-actions?limit=20").json()
        action_types = {action["action_type"] for action in actions}
        assert "governance_pass" in action_types
        assert "governance_pass_accept_duplicate" in action_types


def test_retrieval_scoring_accepts_optional_embedding_score_without_changing_default_weight():
    with TestClient(app) as client:
        memory_response = client.post(
            "/memories",
            json={
                "task_id": "task_embedding_score_boundary",
                "agent_id": "reviewer_1",
                "memory_type": "episodic",
                "scope": "team-shared",
                "content": "Retry policy requires bounded backoff before approval.",
            },
        )
        assert memory_response.status_code == 201
        memory = memory_response.json()

        req = RetrieveRequest(
            task_id="task_embedding_score_boundary",
            agent_id="coder_1",
            agent_role="coder",
            query="bounded retry",
            allowed_scopes=["team-shared"],
        )
        from agentmemos.models import MemoryRecordModel

        model = MemoryRecordModel(**memory)
        score_without_embedding, parts_without_embedding = _score_memory(req, model)
        score_with_embedding, parts_with_embedding = _score_memory(req, model, embedding_score=0.99)

    assert score_with_embedding == score_without_embedding
    assert parts_with_embedding["embedding"] == 0.0
    assert "embedding" not in parts_without_embedding


def test_retrieval_scoring_can_apply_embedding_weight_when_enabled_by_caller():
    with TestClient(app) as client:
        memory_response = client.post(
            "/memories",
            json={
                "task_id": "task_embedding_score_enabled",
                "agent_id": "reviewer_1",
                "memory_type": "episodic",
                "scope": "team-shared",
                "content": "Retry policy requires bounded backoff before approval.",
            },
        )
        assert memory_response.status_code == 201
        memory = memory_response.json()

        req = RetrieveRequest(
            task_id="task_embedding_score_enabled",
            agent_id="coder_1",
            agent_role="coder",
            query="delay strategy",
            allowed_scopes=["team-shared"],
        )
        from agentmemos.models import MemoryRecordModel

        model = MemoryRecordModel(**memory)
        score_without_embedding, _ = _score_memory(req, model)
        score_with_embedding, parts = _score_memory(
            req,
            model,
            embedding_score=0.8,
            embedding_weight=0.1,
        )

    assert parts["embedding"] == pytest.approx(0.08)
    assert score_with_embedding == pytest.approx(score_without_embedding + 0.08)
