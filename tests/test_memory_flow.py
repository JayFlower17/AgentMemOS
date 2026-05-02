from fastapi.testclient import TestClient

from agentmemos.main import app


def test_event_to_retrieval_trace_flow():
    with TestClient(app) as client:
        event_response = client.post(
            "/events",
            json={
                "event_type": "review.finding.created",
                "task_id": "task_test_flow",
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
                "task_id": "task_test_flow",
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
        task_memories = client.get("/memories?task_id=task_test_flow&limit=200").json()
        extracted_memory = next(memory for memory in task_memories if memory["source_event_id"] == source_event_id)
        memory_id = extracted_memory["memory_id"]
        decisions_response = client.get(f"/memories/{memory_id}/decisions")
        assert decisions_response.status_code == 200
        decisions = decisions_response.json()
        assert decisions[0]["decision_type"] == "extracted"
        assert decisions[0]["source_event_id"] == source_event_id
        assert decisions[0]["chosen_scope"] == "team-shared"
        assert "Review findings" in decisions[0]["reason"]


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
