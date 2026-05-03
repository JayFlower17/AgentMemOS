import os
import time
from uuid import uuid4

from agentmemos import AgentMemOSClient


def main() -> None:
    base_url = os.environ.get("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8014")
    client = AgentMemOSClient(base_url)

    before = client._request("GET", "/queue/status")
    task_id = f"task_redis_smoke_{uuid4().hex}"
    event = client.emit_event(
        event_type="review.finding.created",
        task_id=task_id,
        agent_id="reviewer_redis",
        agent_role="reviewer",
        content="The reviewer found that Redis queue smoke tests need bounded worker verification.",
    )

    for _ in range(20):
        memories = client.list_memories(task_id=task_id, limit=20)
        if any(memory["source_event_id"] == event["event_id"] for memory in memories):
            after = client._request("GET", "/queue/status")
            print("queue before:", before)
            print("queue after:", after)
            print("event:", event["event_id"])
            print("memory extracted:", memories[0]["memory_id"])
            return
        time.sleep(0.5)

    after = client._request("GET", "/queue/status")
    raise SystemExit(f"Redis queue smoke test timed out. queue_before={before} queue_after={after}")


if __name__ == "__main__":
    main()
