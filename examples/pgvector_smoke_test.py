import os
import time
from uuid import uuid4

from agentmemos import AgentMemOSClient


def main() -> None:
    base_url = os.environ.get("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8014")
    client = AgentMemOSClient(base_url)
    task_id = f"task_pgvector_smoke_{uuid4().hex}"

    memory = client.create_memory(
        task_id=task_id,
        agent_id="reviewer_pgvector",
        memory_type="episodic",
        scope="team-shared",
        content="Pgvector smoke test memory requires bounded retry backoff before approval.",
        confidence=0.91,
        importance=0.88,
    )

    for _ in range(20):
        result = client.retrieve(
            task_id=task_id,
            agent_id="coder_pgvector",
            agent_role="coder",
            query="bounded retry backoff approval",
            allowed_scopes=["team-shared"],
            limit=5,
        )
        if any(item["memory_id"] == memory["memory_id"] for item in result["memories"]):
            print("memory:", memory["memory_id"])
            print("trace:", result["trace_id"])
            print("packed_context:", result["packed_context"])
            return
        time.sleep(0.5)

    raise SystemExit(f"Pgvector smoke test timed out for memory {memory['memory_id']}")


if __name__ == "__main__":
    main()
