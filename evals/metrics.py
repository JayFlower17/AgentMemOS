from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    retrieved_ids: list[str]
    relevant_ids: set[str]
    latency_ms: float = 0.0

    @property
    def first_relevant_rank(self) -> int | None:
        for index, retrieved_id in enumerate(self.retrieved_ids, start=1):
            if retrieved_id in self.relevant_ids:
                return index
        return None


def recall_at_k(cases: list[RetrievalCaseResult], k: int) -> float:
    evaluable = [case for case in cases if case.relevant_ids]
    if not evaluable:
        return 0.0
    hits = 0
    for case in evaluable:
        if set(case.retrieved_ids[:k]) & case.relevant_ids:
            hits += 1
    return hits / len(evaluable)


def mean_reciprocal_rank(cases: list[RetrievalCaseResult]) -> float:
    evaluable = [case for case in cases if case.relevant_ids]
    if not evaluable:
        return 0.0
    total = 0.0
    for case in evaluable:
        rank = case.first_relevant_rank
        if rank is not None:
            total += 1 / rank
    return total / len(evaluable)


def average_latency_ms(cases: list[RetrievalCaseResult]) -> float:
    if not cases:
        return 0.0
    return sum(case.latency_ms for case in cases) / len(cases)


def retrieval_summary(cases: list[RetrievalCaseResult], *, memory_count: int) -> dict[str, float | int]:
    return {
        "recall_at_1": round(recall_at_k(cases, 1), 4),
        "recall_at_3": round(recall_at_k(cases, 3), 4),
        "recall_at_5": round(recall_at_k(cases, 5), 4),
        "mrr": round(mean_reciprocal_rank(cases), 4),
        "avg_latency_ms": round(average_latency_ms(cases), 2),
        "memory_count": memory_count,
    }

