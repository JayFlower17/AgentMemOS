from fastapi.testclient import TestClient
from uuid import uuid4

from agentmemos.main import app


def test_bm25_and_rerank_prioritize_specific_fact_memory():
    with TestClient(app) as client:
        task_id = f"task_bm25_rerank_test_{uuid4().hex}"
        relevant = client.post(
            "/memories",
            json={
                "task_id": task_id,
                "agent_id": "assistant_1",
                "memory_type": "episodic",
                "scope": "task-local",
                "content": "Caroline went to the LGBTQ support group on 7 May 2023.",
                "summary": "Caroline attended the LGBTQ support group on 7 May 2023.",
                "confidence": 0.7,
                "importance": 0.5,
            },
        ).json()
        client.post(
            "/memories",
            json={
                "task_id": task_id,
                "agent_id": "assistant_1",
                "memory_type": "episodic",
                "scope": "task-local",
                "content": "Caroline discussed dashboard spacing and typography with the team.",
                "summary": "Caroline discussed dashboard layout details.",
                "confidence": 0.95,
                "importance": 0.95,
            },
        )

        response = client.post(
            "/retrieve",
            json={
                "task_id": task_id,
                "agent_id": "reviewer_1",
                "agent_role": "reviewer",
                "query": "When did Caroline go to the LGBTQ support group?",
                "allowed_scopes": ["task-local"],
                "limit": 1,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["memories"][0]["memory_id"] == relevant["memory_id"]
        trace = client.get(f"/traces/{body['trace_id']}").json()
        scored = next(item for item in trace["scored_memories"] if item["memory_id"] == relevant["memory_id"])
        assert scored["score_parts"]["bm25"] > 0
        assert scored["score_parts"]["rerank"] > 0
