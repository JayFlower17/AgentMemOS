from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentmemos import AgentMemOSClient
from evals.locomo_adapter import LocomoSample, load_locomo_samples
from evals.metrics import RetrievalCaseResult, retrieval_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LoCoMo retrieval evaluation against AgentMemOS.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dataset", default="evals/datasets/locomo10.json")
    parser.add_argument("--limit-samples", type=int, default=3)
    parser.add_argument("--limit-questions", type=int, default=30)
    parser.add_argument("--limit-events-per-sample", type=int, default=0)
    parser.add_argument("--mode", choices=["llm", "local"], default="llm")
    parser.add_argument("--wait-timeout", type=float, default=20.0)
    parser.add_argument("--report-dir", default="evals/reports")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = AgentMemOSClient(args.base_url, timeout=20)
    health = client.health()
    if health.get("status") != "ok":
        raise SystemExit(f"AgentMemOS API is not healthy: {health}")

    samples = load_locomo_samples(args.dataset, limit_samples=args.limit_samples)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    case_results: list[RetrievalCaseResult] = []
    report_cases: list[dict[str, Any]] = []
    total_memory_count = 0
    questions_seen = 0

    for sample in samples:
        if questions_seen >= args.limit_questions:
            break
        task_id, event_id_map = replay_sample(
            client,
            sample,
            run_id=run_id,
            limit_events=args.limit_events_per_sample or None,
        )
        memories = wait_for_memories(
            client,
            task_id=task_id,
            expected_source_event_ids=set(event_id_map.values()),
            timeout_seconds=args.wait_timeout,
        )
        total_memory_count += len(memories)
        memories_by_source = {
            memory.get("source_event_id"): memory
            for memory in memories
            if memory.get("source_event_id")
        }
        for question in sample.questions:
            if questions_seen >= args.limit_questions:
                break
            relevant_ids = relevant_memory_ids(question, event_id_map=event_id_map, memories=memories_by_source)
            started = time.perf_counter()
            retrieval = client.retrieve(
                task_id=task_id,
                agent_id="locomo_eval_reviewer",
                agent_role="reviewer",
                query=question.question,
                allowed_scopes=["task-local", "team-shared", "project-global"],
                limit=5,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            retrieved_ids = [memory["memory_id"] for memory in retrieval.get("memories", [])]
            result = RetrievalCaseResult(
                case_id=question.question_id,
                retrieved_ids=retrieved_ids,
                relevant_ids=relevant_ids,
                latency_ms=latency_ms,
            )
            case_results.append(result)
            report_cases.append(
                {
                    "case_id": question.question_id,
                    "sample_id": sample.sample_id,
                    "task_id": task_id,
                    "question": question.question,
                    "answer": question.answer,
                    "trace_id": retrieval.get("trace_id"),
                    "retrieved_memory_ids": retrieved_ids,
                    "relevant_memory_ids": sorted(relevant_ids),
                    "first_relevant_rank": result.first_relevant_rank,
                    "latency_ms": round(latency_ms, 2),
                }
            )
            questions_seen += 1

    report = {
        "dataset": "locomo",
        "mode": args.mode,
        "run_id": run_id,
        "samples": len(samples),
        "questions": len(case_results),
        "metrics": retrieval_summary(case_results, memory_count=total_memory_count),
        "cases": report_cases,
    }
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"locomo_retrieval_{run_id}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("AgentMemOS LoCoMo retrieval eval")
    print(f"mode: {args.mode}")
    print(f"samples: {report['samples']}")
    print(f"questions: {report['questions']}")
    print(f"report: {report_path}")
    for key, value in report["metrics"].items():
        print(f"{key}: {value}")


def replay_sample(
    client: AgentMemOSClient,
    sample: LocomoSample,
    *,
    run_id: str,
    limit_events: int | None = None,
) -> tuple[str, dict[str, str]]:
    task_id = f"{sample.task_id}_{run_id}"
    event_id_map: dict[str, str] = {}
    events = sample.events[:limit_events] if limit_events is not None else sample.events
    for event in events:
        payload = dict(event)
        original_event_id = str(payload["event_id"])
        event_id = f"{original_event_id}_{run_id}"
        event_id_map[original_event_id] = event_id
        payload["event_id"] = event_id
        payload["task_id"] = task_id
        metadata = dict(payload.get("metadata") or {})
        metadata["eval_run_id"] = run_id
        payload["metadata"] = metadata
        client.emit_event(
            event_id=payload["event_id"],
            event_type=payload["event_type"],
            task_id=payload["task_id"],
            agent_id=payload["agent_id"],
            agent_role=payload["agent_role"],
            content=payload["content"],
            metadata=payload["metadata"],
        )
    return task_id, event_id_map


def wait_for_memories(
    client: AgentMemOSClient,
    *,
    task_id: str,
    expected_source_event_ids: set[str],
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        memories = client.list_memories(task_id=task_id, limit=10000)
        source_ids = {memory.get("source_event_id") for memory in memories}
        if expected_source_event_ids.issubset(source_ids):
            return memories
        time.sleep(0.5)
    return client.list_memories(task_id=task_id, limit=10000)


def relevant_memory_ids(
    question,
    *,
    event_id_map: dict[str, str],
    memories: dict[str, dict[str, Any]],
) -> set[str]:
    relevant: set[str] = set()
    for original_event_id in question.evidence_event_ids:
        event_id = event_id_map.get(original_event_id, original_event_id)
        memory = memories.get(event_id)
        if memory:
            relevant.add(memory["memory_id"])
    lowered_texts = [text.casefold() for text in question.evidence_texts if len(text.strip()) >= 8]
    if lowered_texts:
        for memory in memories.values():
            content = f"{memory.get('content', '')} {memory.get('summary', '')}".casefold()
            if any(text in content or content in text for text in lowered_texts):
                relevant.add(memory["memory_id"])
    return relevant


if __name__ == "__main__":
    main()
