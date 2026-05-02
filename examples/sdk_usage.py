import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentmemos import AgentMemOSClient


client = AgentMemOSClient(os.getenv("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8000"))


def main() -> None:
    event = client.emit_event(
        event_type="review.finding.created",
        task_id="task_sdk_demo",
        agent_id="reviewer_1",
        agent_role="reviewer",
        content="Reviewer found that retries need bounded backoff before approval.",
        metadata={"source": "sdk_usage"},
    )
    print("event:", event["event_id"])

    time.sleep(0.5)

    result = client.retrieve(
        task_id="task_sdk_demo",
        agent_id="coder_1",
        agent_role="coder",
        query="bounded backoff approval risk",
        allowed_scopes=["task-local", "team-shared", "project-global"],
    )
    print("trace:", result["trace_id"])
    print(result["packed_context"])


if __name__ == "__main__":
    main()
