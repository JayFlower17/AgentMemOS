import os
import subprocess
import sys
import socket
import time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentmemos import AgentMemOSClient


def wait_for_health(client: AgentMemOSClient, *, timeout_seconds: float = 15.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            if client.health()["status"] == "ok":
                return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("AgentMemOS API did not become healthy in time.")


def read_sse_replay(base_url: str, *, replay: int = 20, timeout_seconds: float = 2.0) -> str:
    request = Request(f"{base_url.rstrip('/')}/events/stream?replay={replay}", headers={"Accept": "text/event-stream"})
    chunks: list[str] = []
    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(request, timeout=timeout_seconds) as response:
            deadline = time.time() + timeout_seconds
            while time.time() < deadline:
                raw = response.readline()
                if not raw:
                    break
                line = raw.decode("utf-8")
                chunks.append(line)
                if "memory.extracted" in line:
                    break
    except (TimeoutError, socket.timeout):
        pass
    return "".join(chunks)


def start_process(args: list[str], *, env: dict[str, str], log_name: str) -> subprocess.Popen:
    log_path = ROOT / log_name
    log_file = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        args,
        cwd=ROOT,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )


def main() -> None:
    base_url = os.environ.get("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8014")
    redis_url = os.environ.get("AGENTMEMOS_REDIS_URL", "redis://localhost:6379/0")
    port = base_url.rsplit(":", 1)[-1]

    try:
        from redis import Redis
    except ImportError as exc:
        raise SystemExit('Redis smoke test requires redis client: pip install "redis>=5"') from exc

    Redis.from_url(redis_url).flushdb()

    env = {
        **os.environ,
        "AGENTMEMOS_JOB_QUEUE_BACKEND": "redis",
        "AGENTMEMOS_REDIS_URL": redis_url,
        "AGENTMEMOS_API_WORKER_ENABLED": "false",
        "AGENTMEMOS_REDIS_EVENT_FANOUT_ENABLED": "true",
    }
    worker_env = {
        **os.environ,
        "AGENTMEMOS_JOB_QUEUE_BACKEND": "redis",
        "AGENTMEMOS_REDIS_URL": redis_url,
        "AGENTMEMOS_REDIS_EVENT_FANOUT_ENABLED": "true",
    }

    api = start_process(
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
        env=env,
        log_name="redis-smoke-api.log",
    )
    worker = start_process(
        [sys.executable, "-m", "agentmemos.worker_app"],
        env=worker_env,
        log_name="redis-smoke-worker.log",
    )

    try:
        client = AgentMemOSClient(base_url)
        wait_for_health(client)
        before = client._request("GET", "/queue/status")
        if before["backend"] != "redis":
            raise RuntimeError(f"Expected Redis queue backend, got {before}")
        if before["worker_running"] is not False:
            raise RuntimeError(f"Expected API worker to be disabled, got {before}")

        task_id = f"task_redis_e2e_{uuid4().hex}"
        event = client.emit_event(
            event_type="review.finding.created",
            task_id=task_id,
            agent_id="reviewer_redis",
            agent_role="reviewer",
            content="The reviewer found that Redis E2E smoke tests need independent worker verification.",
        )

        for _ in range(30):
            memories = client.list_memories(task_id=task_id, limit=20)
            extracted = [memory for memory in memories if memory["source_event_id"] == event["event_id"]]
            if extracted:
                after = client._request("GET", "/queue/status")
                sse_replay = read_sse_replay(base_url, replay=30)
                if "memory.extracted" not in sse_replay:
                    raise RuntimeError(f"Expected worker memory.extracted event in SSE replay, got: {sse_replay}")
                print("queue before:", before)
                print("queue after:", after)
                print("event:", event["event_id"])
                print("memory extracted:", extracted[0]["memory_id"])
                print("sse fanout: memory.extracted observed")
                return
            time.sleep(0.5)

        after = client._request("GET", "/queue/status")
        raise RuntimeError(f"Timed out waiting for Redis worker extraction. before={before} after={after}")
    finally:
        for process in (worker, api):
            process.terminate()
        for process in (worker, api):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
