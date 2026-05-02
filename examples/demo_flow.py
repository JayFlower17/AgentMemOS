import time
import os

import httpx


BASE_URL = os.getenv("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8000")


events = [
    {
        "event_type": "task.created",
        "task_id": "task_demo",
        "agent_id": "planner_1",
        "agent_role": "planner",
        "content": "Build the AgentMemOS MVP with event ingestion, scoped memory, retrieval traces, and role-aware context.",
    },
    {
        "event_type": "tool.result.observed",
        "task_id": "task_demo",
        "agent_id": "coder_1",
        "agent_role": "coder",
        "content": "Initial test run failed because the retrieval endpoint returned another agent's local scratch memory.",
    },
    {
        "event_type": "review.finding.created",
        "task_id": "task_demo",
        "agent_id": "reviewer_1",
        "agent_role": "reviewer",
        "content": "Reviewer should check that agent-local memories are only visible to the same agent.",
    },
]


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=10, trust_env=False) as client:
        for event in events:
            response = client.post("/events", json=event)
            response.raise_for_status()
            print("event", response.json()["event_id"])

        time.sleep(0.5)

        response = client.post(
            "/retrieve",
            json={
                "task_id": "task_demo",
                "agent_id": "reviewer_1",
                "agent_role": "reviewer",
                "query": "What risks should I check before approving this change?",
                "allowed_scopes": ["task-local", "team-shared", "project-global"],
            },
        )
        response.raise_for_status()
        data = response.json()
        print("\ntrace:", data["trace_id"])
        print(data["packed_context"])


if __name__ == "__main__":
    main()
