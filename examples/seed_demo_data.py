import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentmemos import AgentMemOSClient


BASE_URL = os.getenv("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8014")


EVENTS = [
    {
        "event_type": "task.created",
        "task_id": "task_demo",
        "agent_id": "planner_1",
        "agent_role": "planner",
        "content": "Plan the AgentMemOS dashboard upgrade so memory write decisions and retrieval traces are both auditable.",
        "metadata": {"seed": "dashboard-memory-decisions"},
    },
    {
        "event_type": "subtask.completed",
        "task_id": "task_demo",
        "agent_id": "planner_1",
        "agent_role": "planner",
        "content": "Planner confirmed the next milestone is a dashboard panel for memory write decision traces.",
        "metadata": {"seed": "dashboard-memory-decisions"},
    },
    {
        "event_type": "tool.result.observed",
        "task_id": "task_demo",
        "agent_id": "coder_1",
        "agent_role": "coder",
        "content": "Coder observed that old manual memories have sparse decision signals because they were created directly through the API.",
        "metadata": {"seed": "dashboard-memory-decisions"},
    },
    {
        "event_type": "tool.result.observed",
        "task_id": "task_demo",
        "agent_id": "reviewer_1",
        "agent_role": "reviewer",
        "content": "Reviewer observed the decision panel should explain event_type, agent_role, memory_type, scope, confidence, and importance.",
        "metadata": {"seed": "dashboard-memory-decisions"},
    },
    {
        "event_type": "review.finding.created",
        "task_id": "task_demo",
        "agent_id": "reviewer_1",
        "agent_role": "reviewer",
        "content": "Reviewer found that extracted memories need clearer signals than manual memories for convincing demos.",
        "metadata": {"seed": "dashboard-memory-decisions"},
    },
    {
        "event_type": "review.finding.created",
        "task_id": "task_demo",
        "agent_id": "reviewer_1",
        "agent_role": "reviewer",
        "content": "Reviewer found that filtered agent-local scratch should be collapsed in the trace explain panel.",
        "metadata": {"seed": "dashboard-memory-decisions"},
    },
    {
        "event_type": "task.completed",
        "task_id": "task_demo",
        "agent_id": "planner_1",
        "agent_role": "planner",
        "content": "When demoing AgentMemOS, seed extracted events first, then inspect write decisions before retrieval traces.",
        "metadata": {"seed": "dashboard-memory-decisions"},
    },
    {
        "event_type": "task.created",
        "task_id": "task_checkout",
        "agent_id": "planner_1",
        "agent_role": "planner",
        "content": "Coordinate a checkout refactor with planner, coder, and reviewer memories separated by scope.",
        "metadata": {"seed": "checkout-refactor"},
    },
    {
        "event_type": "tool.result.observed",
        "task_id": "task_checkout",
        "agent_id": "coder_2",
        "agent_role": "coder",
        "content": "Coder discovered the checkout retry test fails when the fixture path is resolved relative to the wrong package root.",
        "metadata": {"seed": "checkout-refactor"},
    },
    {
        "event_type": "review.finding.created",
        "task_id": "task_checkout",
        "agent_id": "reviewer_2",
        "agent_role": "reviewer",
        "content": "Reviewer flagged that checkout retry behavior must bound backoff and preserve idempotency.",
        "metadata": {"seed": "checkout-refactor"},
    },
]


MANUAL_MEMORIES = [
    {
        "task_id": "task_demo",
        "agent_id": "planner_1",
        "memory_type": "procedural",
        "scope": "project-global",
        "content": "Demo rule: prefer extracted event memories when showing decision traces because they include richer signals.",
        "summary": "Prefer extracted memories for decision-trace demos.",
        "confidence": 0.88,
        "importance": 0.76,
    },
    {
        "task_id": "task_checkout",
        "agent_id": "reviewer_2",
        "memory_type": "procedural",
        "scope": "team-shared",
        "content": "Checkout retry reviews should verify bounded backoff, idempotency, and fixture paths before approval.",
        "summary": "Checkout retry review checklist.",
        "confidence": 0.84,
        "importance": 0.82,
    },
]


RETRIEVALS = [
    {
        "task_id": "task_demo",
        "agent_id": "reviewer_1",
        "agent_role": "reviewer",
        "query": "What should I inspect in the memory decision dashboard demo?",
        "allowed_scopes": ["task-local", "team-shared", "project-global"],
    },
    {
        "task_id": "task_demo",
        "agent_id": "coder_1",
        "agent_role": "coder",
        "query": "Why do manual memories have sparse decision signals?",
        "allowed_scopes": ["agent-local", "task-local", "team-shared", "project-global"],
    },
    {
        "task_id": "task_checkout",
        "agent_id": "reviewer_2",
        "agent_role": "reviewer",
        "query": "What checkout retry risks should be reviewed before approval?",
        "allowed_scopes": ["task-local", "team-shared", "project-global"],
    },
]


def main() -> None:
    client = AgentMemOSClient(BASE_URL)
    print(f"Seeding demo data into {BASE_URL}")

    for event in EVENTS:
        created = client.emit_event(**event)
        print("event", created["event_id"], event["event_type"], event["task_id"])

    time.sleep(1.0)

    for memory in MANUAL_MEMORIES:
        created = client.create_memory(**memory)
        print("memory", created["memory_id"], memory["memory_type"], memory["scope"])

    for retrieval in RETRIEVALS:
        result = client.retrieve(**retrieval)
        print("trace", result["trace_id"], retrieval["task_id"], len(result["memories"]))


if __name__ == "__main__":
    main()
