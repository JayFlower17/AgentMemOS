from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentmemos import AgentMemOSClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AgentMemOS governance relation evaluation.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dataset", default="evals/datasets/agentmemos_governance_gold.json")
    parser.add_argument("--mode", choices=["llm", "local"], default="llm")
    parser.add_argument("--report-dir", default="evals/reports")
    parser.add_argument("--no-direct-supersedes-verification", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = AgentMemOSClient(args.base_url, timeout=20)
    health = client.health()
    if health.get("status") != "ok":
        raise SystemExit(f"AgentMemOS API is not healthy: {health}")

    cases = load_gold_cases(args.dataset)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    case_reports = []
    expected_by_type = Counter(case["expected_relation"] for case in cases)
    hits_by_type: Counter[str] = Counter()
    predicted_by_type: Counter[str] = Counter()
    false_positive_count = 0

    for case in cases:
        task_id = f"{case['task_id']}_{run_id}_{case['case_id']}"
        label_to_memory = create_case_memories(client, case, task_id=task_id)
        suggestions = client.list_relation_suggestions(task_id=task_id, limit=50)
        expected = expected_relation_payload(case, label_to_memory)
        matching = [suggestion for suggestion in suggestions if suggestion_matches(suggestion, expected)]
        for suggestion in suggestions:
            predicted_by_type[suggestion["relation_type"]] += 1
        false_positive_count += sum(1 for suggestion in suggestions if not suggestion_matches(suggestion, expected))

        accepted = None
        verification = None
        direct_verification = False
        if matching:
            hits_by_type[case["expected_relation"]] += 1
            accepted = client.accept_relation_suggestion(
                matching[0]["suggestion_id"],
                actor="governance_eval",
                reason="Accepted during governance evaluation.",
            )
        elif case["expected_relation"] == "supersedes" and not args.no_direct_supersedes_verification:
            direct_verification = True
            accepted = {
                "relation": client.create_memory_relation(
                    source_memory_id=expected["source_memory_id"],
                    target_memory_id=expected["target_memory_id"],
                    relation_type="supersedes",
                    reason="Direct verification relation for supersedes retrieval filtering.",
                ),
                "action": None,
            }

        if accepted and case["expected_relation"] == "supersedes":
            verification = verify_supersedes_filtering(client, task_id=task_id, expected=expected)

        case_reports.append(
            {
                "case_id": case["case_id"],
                "task_id": task_id,
                "expected": expected,
                "suggestions": suggestions,
                "matched": bool(matching),
                "accepted_relation": accepted["relation"] if accepted else None,
                "direct_verification": direct_verification,
                "verification": verification,
            }
        )

    metrics = relation_metrics(expected_by_type, predicted_by_type, hits_by_type, false_positive_count)
    report = {
        "dataset": "agentmemos_governance_gold",
        "mode": args.mode,
        "run_id": run_id,
        "cases": case_reports,
        "metrics": metrics,
    }
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"governance_eval_{run_id}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("AgentMemOS governance eval")
    print(f"mode: {args.mode}")
    print(f"cases: {len(cases)}")
    print(f"report: {report_path}")
    for key, value in metrics.items():
        print(f"{key}: {value}")


def load_gold_cases(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as dataset_file:
        data = json.load(dataset_file)
    cases = data.get("cases", data)
    if not isinstance(cases, list):
        raise ValueError("Governance gold dataset must be a list or an object with cases")
    return cases


def create_case_memories(
    client: AgentMemOSClient,
    case: dict[str, Any],
    *,
    task_id: str,
) -> dict[str, dict[str, Any]]:
    label_to_memory: dict[str, dict[str, Any]] = {}
    for item in case["memories"]:
        memory = client.create_memory(
            task_id=task_id,
            agent_id=item.get("agent_id", "governance_eval"),
            memory_type=item.get("memory_type", "episodic"),
            scope=item.get("scope", "team-shared"),
            content=item["content"],
            summary=item.get("summary"),
            confidence=float(item.get("confidence", 0.82)),
            importance=float(item.get("importance", 0.8)),
        )
        label_to_memory[item["label"]] = memory
    return label_to_memory


def expected_relation_payload(case: dict[str, Any], label_to_memory: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        "relation_type": case["expected_relation"],
        "source_memory_id": label_to_memory[case["source_label"]]["memory_id"],
        "target_memory_id": label_to_memory[case["target_label"]]["memory_id"],
    }


def suggestion_matches(suggestion: dict[str, Any], expected: dict[str, str]) -> bool:
    if suggestion["relation_type"] != expected["relation_type"]:
        return False
    actual_pair = {suggestion["source_memory_id"], suggestion["target_memory_id"]}
    expected_pair = {expected["source_memory_id"], expected["target_memory_id"]}
    if suggestion["relation_type"] in {"duplicates", "conflicts_with"}:
        return actual_pair == expected_pair
    return (
        suggestion["source_memory_id"] == expected["source_memory_id"]
        and suggestion["target_memory_id"] == expected["target_memory_id"]
    )


def verify_supersedes_filtering(
    client: AgentMemOSClient,
    *,
    task_id: str,
    expected: dict[str, str],
) -> dict[str, Any]:
    retrieval = client.retrieve(
        task_id=task_id,
        agent_id="governance_eval_reviewer",
        agent_role="reviewer",
        query="bounded retry backoff approval guidance",
        allowed_scopes=["team-shared"],
        limit=5,
    )
    trace = client.get_trace(retrieval["trace_id"])
    target_id = expected["target_memory_id"]
    filter_reason = (trace.get("filter_reasons") or {}).get(target_id, "")
    return {
        "trace_id": retrieval["trace_id"],
        "target_filtered": target_id in (trace.get("filtered_memories") or []),
        "filter_reason": filter_reason,
        "selected_memory_ids": trace.get("selected_memories") or [],
    }


def relation_metrics(
    expected_by_type: Counter[str],
    predicted_by_type: Counter[str],
    hits_by_type: Counter[str],
    false_positive_count: int,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {"false_positive_count": false_positive_count}
    for relation_type in sorted(set(expected_by_type) | set(predicted_by_type)):
        expected = expected_by_type[relation_type]
        predicted = predicted_by_type[relation_type]
        hits = hits_by_type[relation_type]
        metrics[f"{relation_type}_precision"] = round(hits / predicted, 4) if predicted else 0.0
        metrics[f"{relation_type}_recall"] = round(hits / expected, 4) if expected else 0.0
    metrics["macro_recall"] = round(
        sum((hits_by_type[key] / expected_by_type[key]) if expected_by_type[key] else 0 for key in expected_by_type)
        / max(1, len(expected_by_type)),
        4,
    )
    return metrics


if __name__ == "__main__":
    main()

