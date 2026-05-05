"""Lightweight concurrent event ingestion load test.

Run against a started AgentMemOS API:

    python examples/load_test_events.py --requests 100 --concurrency 20

The script uses only the standard library and avoids system proxy settings so
localhost tests are not affected by desktop proxy configuration.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def request_json(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    opener = build_opener(ProxyHandler({}))
    with opener.open(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def emit_event(base_url: str, *, task_id: str, index: int) -> dict[str, Any]:
    payload = {
        "event_type": "review.finding.created",
        "task_id": task_id,
        "agent_id": f"load_reviewer_{index % 8}",
        "agent_role": "reviewer",
        "content": (
            f"Load test finding {index}: retries need bounded backoff before approval "
            "and should be retained for downstream coding context."
        ),
        "event_metadata": {"load_test_index": index},
    }
    started = time.perf_counter()
    try:
        response = request_json(base_url, "POST", "/events", payload)
        ok = True
        error = ""
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        response = {}
        ok = False
        error = str(exc)
    latency_ms = (time.perf_counter() - started) * 1000
    return {"ok": ok, "latency_ms": latency_ms, "response": response, "error": error}


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((percent / 100) * (len(ordered) - 1)))))
    return ordered[index]


def wait_for_queue_progress(base_url: str, *, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_status: dict[str, Any] = {}
    while time.time() < deadline:
        try:
            last_status = request_json(base_url, "GET", "/queue/status")
        except Exception:
            time.sleep(0.25)
            continue
        pending = int(last_status.get("pending", 0))
        enqueued = int(last_status.get("enqueued", 0))
        completed = int(last_status.get("completed", 0))
        dead_lettered = int(last_status.get("dead_lettered", 0))
        if pending == 0 and completed >= enqueued and dead_lettered == 0:
            return last_status
        time.sleep(0.5)
    return last_status


def main() -> None:
    parser = argparse.ArgumentParser(description="Concurrent AgentMemOS event ingestion load test.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8014")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--wait-seconds", type=float, default=20)
    args = parser.parse_args()

    task_id = f"task_load_{uuid4().hex}"
    before = request_json(args.base_url, "GET", "/queue/status")
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(emit_event, args.base_url, task_id=task_id, index=index) for index in range(args.requests)]
        results = [future.result() for future in as_completed(futures)]
    elapsed_seconds = time.perf_counter() - started

    successes = [result for result in results if result["ok"]]
    failures = [result for result in results if not result["ok"]]
    latencies = [float(result["latency_ms"]) for result in results]
    after = wait_for_queue_progress(args.base_url, timeout_seconds=args.wait_seconds)

    print("AgentMemOS event ingestion load test")
    print(f"base_url: {args.base_url}")
    print(f"task_id: {task_id}")
    print(f"requests: {args.requests}")
    print(f"concurrency: {args.concurrency}")
    print(f"success: {len(successes)}")
    print(f"failed: {len(failures)}")
    print(f"elapsed_seconds: {elapsed_seconds:.3f}")
    print(f"throughput_rps: {args.requests / elapsed_seconds:.2f}")
    print(f"latency_avg_ms: {statistics.mean(latencies):.2f}")
    print(f"latency_p95_ms: {percentile(latencies, 95):.2f}")
    print(f"latency_max_ms: {max(latencies):.2f}")
    print(f"queue_before: {before}")
    print(f"queue_after: {after}")
    if failures:
        print("first_error:", failures[0]["error"])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
