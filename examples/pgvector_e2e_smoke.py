import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentmemos import AgentMemOSClient


def wait_for_health(client: AgentMemOSClient, *, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            if client.health()["status"] == "ok":
                return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("AgentMemOS API did not become healthy in time.")


def start_api(*, base_url: str, pgvector_url: str) -> subprocess.Popen:
    port = base_url.rsplit(":", 1)[-1]
    env = {
        **os.environ,
        "AGENTMEMOS_VECTOR_STORE_BACKEND": "pgvector",
        "AGENTMEMOS_PGVECTOR_URL": pgvector_url,
        "AGENTMEMOS_PGVECTOR_DIMENSIONS": "64",
        "AGENTMEMOS_VECTOR_RETRIEVAL_ENABLED": "true",
        "AGENTMEMOS_VECTOR_RETRIEVAL_WEIGHT": "0.1",
    }
    log_file = (ROOT / "pgvector-smoke-api.log").open("w", encoding="utf-8")
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "agentmemos.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            port,
        ],
        cwd=ROOT,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )


def main() -> None:
    base_url = os.environ.get("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8014")
    pgvector_url = os.environ.get(
        "AGENTMEMOS_PGVECTOR_URL",
        "postgresql://agentmemos:agentmemos@localhost:5432/agentmemos",
    )

    api = start_api(base_url=base_url, pgvector_url=pgvector_url)
    try:
        client = AgentMemOSClient(base_url)
        wait_for_health(client)
        task_id = f"task_pgvector_e2e_{uuid4().hex}"

        memory = client.create_memory(
            task_id=task_id,
            agent_id="reviewer_pgvector",
            memory_type="episodic",
            scope="team-shared",
            content="Pgvector E2E smoke test memory requires bounded retry backoff before approval.",
            confidence=0.91,
            importance=0.88,
        )

        for _ in range(30):
            result = client.retrieve(
                task_id=task_id,
                agent_id="coder_pgvector",
                agent_role="coder",
                query="bounded retry backoff approval",
                allowed_scopes=["team-shared"],
                limit=5,
            )
            if any(item["memory_id"] == memory["memory_id"] for item in result["memories"]):
                trace = client.get_trace(result["trace_id"])
                scored = next(item for item in trace["scored_memories"] if item["memory_id"] == memory["memory_id"])
                if scored["score_parts"].get("embedding", 0) <= 0:
                    raise RuntimeError(f"Expected vector score contribution in trace, got {scored}")
                print("memory:", memory["memory_id"])
                print("trace:", result["trace_id"])
                print("embedding score contribution:", scored["score_parts"]["embedding"])
                print("packed_context:", result["packed_context"])
                return
            time.sleep(0.5)

        raise RuntimeError(f"Pgvector E2E smoke test timed out for memory {memory['memory_id']}")
    finally:
        api.terminate()
        try:
            api.wait(timeout=5)
        except subprocess.TimeoutExpired:
            api.kill()


if __name__ == "__main__":
    main()
