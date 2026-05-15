"""Interview-friendly AgentMemOS demo.

This script demonstrates the core loop without requiring external LLM keys:

1. Emit agent events.
2. Wait for extracted memories.
3. Create explicit memories for governance examples.
4. Archive one memory and show retrieval governance filtering.
5. Retrieve scoped memory context and inspect trace reasons.
6. Generate and accept a duplicate relation suggestion.

Run with a local API:

    $env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8014"; python examples/interview_demo.py
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentmemos import AgentMemOSClient
from agentmemos.sdk import AgentMemOSError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an interview-friendly AgentMemOS system demo.")
    parser.add_argument("--base-url", default=os.getenv("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--mode", choices=["llm", "local"], default=os.getenv("AGENTMEMOS_DEMO_MODE", "llm"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--wait-timeout", type=float, default=8.0)
    parser.add_argument("--print-dashboard-url", action="store_true", default=False)
    return parser.parse_args()


def wait_for_extracted_memories(
    client: AgentMemOSClient,
    *,
    task_id: str,
    source_event_ids: set[str],
    timeout_seconds: float = 8.0,
) -> list[dict]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        memories = client.list_memories(task_id=task_id, limit=200)
        extracted = [memory for memory in memories if memory.get("source_event_id") in source_event_ids]
        if len(extracted) >= len(source_event_ids):
            return extracted
        time.sleep(0.4)
    return client.list_memories(task_id=task_id, limit=200)


def print_memory(memory: dict) -> None:
    print(
        f"- {memory['memory_id']} [{memory['scope']}/{memory['memory_type']}/{memory['status']}] "
        f"{memory['summary']}"
    )


def main() -> None:
    args = parse_args()
    base_url = args.base_url
    client = AgentMemOSClient(base_url, timeout=max(12, args.wait_timeout))
    try:
        health = client.health()
    except AgentMemOSError as exc:
        raise SystemExit(f"AgentMemOS API is not reachable at {base_url}: {exc}") from exc
    if health.get("status") != "ok":
        raise SystemExit(f"AgentMemOS API is not healthy: {health}")

    task_id = args.task_id or f"task_interview_demo_{uuid4().hex[:8]}"
    print("AgentMemOS interview demo")
    print(f"base_url: {base_url}")
    print(f"mode: {args.mode}")
    print(f"task_id: {task_id}")
    if args.print_dashboard_url:
        print(f"dashboard: {base_url.rstrip('/')}/")
    if args.mode == "llm":
        print("expected server mode: OpenAI-compatible extractor/governance/embedding when configured")
    else:
        print("expected server mode: rule extractor + hashing embedding fallback")

    print("\n1) Emit planner/coder/reviewer events")
    events = [
        client.emit_event(
            event_type="task.created",
            task_id=task_id,
            agent_id="planner_demo",
            agent_role="planner",
            content="Plan: update the dashboard while preserving trace explain, memory governance, and queue status visibility.",
        ),
        client.emit_event(
            event_type="review.finding.created",
            task_id=task_id,
            agent_id="reviewer_demo",
            agent_role="reviewer",
            content="The reviewer found that retries need bounded backoff before approval.",
        ),
        client.emit_event(
            event_type="tool.result.observed",
            task_id=task_id,
            agent_id="coder_demo",
            agent_role="coder",
            content="The coder saw a failing test: trace explain must keep selected memories, score parts, and filtered memory reasons visible.",
        ),
        client.emit_event(
            event_type="task.completed",
            task_id=task_id,
            agent_id="coder_demo",
            agent_role="coder",
            content="When Redis queue is enabled, run an independent worker and verify queue status after extraction.",
        ),
    ]
    source_event_ids = {event["event_id"] for event in events}
    for event in events:
        print(f"- event: {event['event_id']} ({event['event_type']})")

    print("\n2) Wait for worker extraction")
    memories = wait_for_extracted_memories(
        client,
        task_id=task_id,
        source_event_ids=source_event_ids,
        timeout_seconds=args.wait_timeout,
    )
    for memory in memories:
        print_memory(memory)

    print("\n3) Create explicit memories for governance examples")
    archived = client.create_memory(
        task_id=task_id,
        agent_id="reviewer_demo",
        memory_type="episodic",
        scope="team-shared",
        content="Old guidance: approval can proceed without bounded retry backoff.",
        summary="Old approval guidance without bounded retry backoff.",
        confidence=0.7,
        importance=0.85,
    )
    client.archive_memory(archived["memory_id"], reason="Interview demo: old retry guidance is no longer valid.")
    print(f"- archived memory: {archived['memory_id']}")

    duplicate_a = client.create_memory(
        task_id=task_id,
        agent_id="reviewer_demo",
        memory_type="episodic",
        scope="team-shared",
        content="Redis queue decouples memory extraction and embedding indexing from API writes.",
        summary="Redis queue decouples memory jobs from API writes.",
        confidence=0.82,
        importance=0.8,
    )
    duplicate_b = client.create_memory(
        task_id=task_id,
        agent_id="reviewer_demo",
        memory_type="episodic",
        scope="team-shared",
        content="Redis queue decouples memory extraction and embedding indexing from API writes for AgentMemOS.",
        summary="Redis queue decouples memory jobs from API writes in AgentMemOS.",
        confidence=0.8,
        importance=0.78,
    )
    print(f"- duplicate candidate A: {duplicate_a['memory_id']}")
    print(f"- duplicate candidate B: {duplicate_b['memory_id']}")

    print("\n4) Reviewer retrieves context and inspects trace")
    retrieval = client.retrieve(
        task_id=task_id,
        agent_id="reviewer_demo",
        agent_role="reviewer",
        query="dashboard trace explain selected memories filtered reasons bounded backoff Redis queue extraction indexing",
        allowed_scopes=["task-local", "team-shared"],
        limit=5,
    )
    print(f"trace_id: {retrieval['trace_id']}")
    print("packed_context:")
    print(retrieval["packed_context"] or "(empty)")

    trace = client.get_trace(retrieval["trace_id"])
    print("trace reason:")
    print(trace["reason"])
    print("selected memories:")
    for memory_id in trace.get("selected_memories") or []:
        print(f"- {memory_id}")
    print("scored memories:")
    for item in (trace.get("scored_memories") or [])[:5]:
        print(f"- {item['memory_id']} score={item['score']} selected={item['selected']} parts={item.get('score_parts')}")
    print("filtered memories:")
    for memory_id, reason in (trace.get("filter_reasons") or {}).items():
        print(f"- {memory_id}: {reason}")

    print("\n5) Governance suggestions")
    suggestions = client.list_relation_suggestions(task_id=task_id, limit=10)
    if not suggestions:
        print("- no relation suggestions")
    for suggestion in suggestions:
        print(
            f"- {suggestion['suggestion_id']} {suggestion['relation_type']} "
            f"{suggestion['confidence']}: {suggestion['reason']}"
        )

    duplicate = next((item for item in suggestions if item["relation_type"] == "duplicates"), None)
    if duplicate:
        accepted = client.accept_relation_suggestion(
            duplicate["suggestion_id"],
            actor="interview_demo",
            reason="Accepted in interview demo to show audited governance flow.",
        )
        print("accepted duplicate suggestion:")
        print(f"- relation: {accepted['relation']['relation_id']}")
        print(f"- action: {accepted['action']['action_id']}")

    print("\n6) Supersedes relation filters old guidance")
    newer = client.create_memory(
        task_id=task_id,
        agent_id="reviewer_demo",
        memory_type="episodic",
        scope="team-shared",
        content="Updated guidance: approval requires bounded retry backoff and trace explain must show filtered reasons.",
        summary="Approval requires bounded retry backoff and trace filter reasons.",
        confidence=0.88,
        importance=0.92,
    )
    relation = client.create_memory_relation(
        source_memory_id=newer["memory_id"],
        target_memory_id=archived["memory_id"],
        relation_type="supersedes",
        reason="The updated interview guidance replaces old retry approval guidance.",
    )
    supersedes_retrieval = client.retrieve(
        task_id=task_id,
        agent_id="reviewer_demo",
        agent_role="reviewer",
        query="approval bounded retry backoff filtered reasons",
        allowed_scopes=["team-shared"],
        limit=5,
    )
    supersedes_trace = client.get_trace(supersedes_retrieval["trace_id"])
    print(f"- supersedes relation: {relation['relation_id']}")
    print(f"- updated memory: {newer['memory_id']}")
    print(f"- supersedes trace: {supersedes_retrieval['trace_id']}")
    for memory_id, reason in (supersedes_trace.get("filter_reasons") or {}).items():
        print(f"- filtered {memory_id}: {reason}")

    print("\n7) Queue and governance status")
    queue_status = client._request("GET", "/queue/status")
    print(
        "queue:",
        {
            "backend": queue_status["backend"],
            "pending": queue_status["pending"],
            "completed": queue_status["completed"],
            "failed": queue_status["failed"],
            "dead_lettered": queue_status["dead_lettered"],
            "worker_concurrency": queue_status["worker_concurrency"],
        },
    )
    actions = client.list_governance_actions(limit=5)
    print(f"recent governance actions: {len(actions)}")
    print("\nInterview anchors:")
    print(f"- dashboard: {base_url.rstrip('/')}/")
    print(f"- main trace: {retrieval['trace_id']}")
    print(f"- supersedes trace: {supersedes_retrieval['trace_id']}")
    print(f"- task_id: {task_id}")
    print("\nDemo complete.")


if __name__ == "__main__":
    main()
