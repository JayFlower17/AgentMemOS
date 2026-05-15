from hashlib import sha1
import json
from typing import Any, Callable, Protocol
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentmemos.enums import MemoryStatus
from agentmemos.models import (
    MemoryGovernanceActionModel,
    MemoryRecordModel,
    MemoryRelationModel,
    MemoryStatusDecisionModel,
    RetrievalTraceModel,
    utcnow,
)
from agentmemos.schemas import (
    AcceptMemoryRelationSuggestionResponse,
    MemoryInsight,
    MemoryRelationSuggestion,
    RunGovernanceRequest,
    RunGovernanceResponse,
)
from agentmemos.serializers import memory_governance_action_to_schema, memory_relation_to_schema


GovernanceReviewTransport = Callable[[dict[str, Any]], dict[str, Any]]


class GovernanceReviewerProvider(Protocol):
    name: str

    def suggest(
        self,
        db: Session,
        left: MemoryRecordModel,
        right: MemoryRecordModel,
    ) -> MemoryRelationSuggestion | None: ...


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{sha1('|'.join(parts).encode()).hexdigest()[:16]}"


def relation_insight(relation: MemoryRelationModel, source: MemoryRecordModel | None) -> MemoryInsight:
    task_id = source.task_id if source else None
    relation_labels = {
        "conflicts_with": ("high", "Open memory conflict needs resolution."),
        "duplicates": ("medium", "Possible duplicate memories should be merged or canonicalized."),
        "supersedes": ("low", "Superseded memory is waiting for governance review."),
    }
    severity, summary = relation_labels.get(relation.relation_type, ("low", "Open memory relation needs review."))
    return MemoryInsight(
        insight_id=_stable_id("insight", "relation", relation.relation_id, relation.status),
        insight_type=f"open_{relation.relation_type}",
        severity=severity,
        summary=summary,
        memory_ids=[relation.source_memory_id, relation.target_memory_id],
        evidence={
            "relation_id": relation.relation_id,
            "relation_type": relation.relation_type,
            "task_id": task_id,
            "reason": relation.reason,
        },
        suggested_action="Review the relation and resolve it once the canonical memory state is clear.",
        created_at=relation.created_at,
    )


def trace_insights(trace: RetrievalTraceModel) -> list[MemoryInsight]:
    insights: list[MemoryInsight] = []
    if not trace.selected_memories:
        insights.append(
            MemoryInsight(
                insight_id=_stable_id("insight", "trace-miss", trace.trace_id),
                insight_type="retrieval_miss",
                severity="medium",
                summary="Retrieval returned no memories for this request.",
                trace_ids=[trace.trace_id],
                evidence={"task_id": trace.task_id, "agent_role": trace.agent_role, "query": trace.query},
                suggested_action="Inspect whether the task lacks useful memory, the query is too narrow, or scope filters are too restrictive.",
                created_at=trace.created_at,
            )
        )
    for item in trace.scored_memories or []:
        if not item.get("selected"):
            continue
        score = float(item.get("score") or 0)
        if score < 0.45:
            insights.append(
                MemoryInsight(
                    insight_id=_stable_id("insight", "low-score", trace.trace_id, item.get("memory_id", "")),
                    insight_type="low_confidence_selection",
                    severity="low",
                    summary="Retrieval selected a low-scoring memory.",
                    memory_ids=[item.get("memory_id", "")],
                    trace_ids=[trace.trace_id],
                    evidence={"score": score, "score_parts": item.get("score_parts", {}), "query": trace.query},
                    suggested_action="Ask an agent to verify whether the selected memory is useful, stale, or under-scored.",
                    created_at=trace.created_at,
                )
            )
        if item.get("governance"):
            insights.append(
                MemoryInsight(
                    insight_id=_stable_id("insight", "governance-warning", trace.trace_id, item.get("memory_id", "")),
                    insight_type="governance_warning_selected",
                    severity="medium",
                    summary="Retrieval selected a memory with open governance relations.",
                    memory_ids=[item.get("memory_id", "")],
                    trace_ids=[trace.trace_id],
                    evidence={"governance": item.get("governance"), "query": trace.query},
                    suggested_action="Review the open relation before treating this memory as fully settled.",
                    created_at=trace.created_at,
                )
            )
    return insights


def memory_terms(memory: MemoryRecordModel) -> set[str]:
    stopwords = {
        "the",
        "and",
        "for",
        "that",
        "with",
        "this",
        "from",
        "should",
        "before",
        "after",
        "memory",
        "reviewer",
    }
    words = []
    for raw in f"{memory.summary} {memory.content}".lower().replace(".", " ").replace(",", " ").split():
        token = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_"})
        if len(token) > 2 and token not in stopwords:
            words.append(token)
    return set(words)


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def has_existing_relation(db: Session, left_id: str, right_id: str, relation_type: str) -> bool:
    stmt = select(MemoryRelationModel).where(
        MemoryRelationModel.relation_type == relation_type,
        (
            (
                (MemoryRelationModel.source_memory_id == left_id)
                & (MemoryRelationModel.target_memory_id == right_id)
            )
            | (
                (MemoryRelationModel.source_memory_id == right_id)
                & (MemoryRelationModel.target_memory_id == left_id)
            )
        ),
    )
    return db.scalar(stmt) is not None


def relation_suggestion_id(relation_type: str, source_id: str, target_id: str) -> str:
    return _stable_id("suggest", relation_type, source_id, target_id)


class RuleBasedGovernanceReviewer:
    name = "rule"

    def suggest(
        self,
        db: Session,
        left: MemoryRecordModel,
        right: MemoryRecordModel,
    ) -> MemoryRelationSuggestion | None:
        return _rule_suggest_relation_for_pair(db, left, right)


class OpenAIGovernanceReviewer:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 20.0,
        min_confidence: float = 0.7,
        transport: GovernanceReviewTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.min_confidence = min_confidence
        self.transport = transport

    def suggest(
        self,
        db: Session,
        left: MemoryRecordModel,
        right: MemoryRecordModel,
    ) -> MemoryRelationSuggestion | None:
        if not self.api_key and self.transport is None:
            return None
        try:
            raw = self._call_model(left, right)
            suggestion = self._suggestion_from_model(left, right, raw)
        except Exception:
            return None
        if suggestion is None:
            return None
        if has_existing_relation(db, suggestion.source_memory_id, suggestion.target_memory_id, suggestion.relation_type):
            return None
        return suggestion

    def _call_model(self, left: MemoryRecordModel, right: MemoryRecordModel) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an AgentMemOS memory governance reviewer. Return only JSON. "
                        "You only generate governance suggestions; you never mutate memory state. "
                        "Choose relation_type as one of duplicates, conflicts_with, supersedes, none. "
                        "Use duplicates when memories express the same reusable knowledge. "
                        "Use conflicts_with when both memories cannot be true in the same scope. "
                        "Use supersedes when the source memory clearly replaces the target memory. "
                        "Use none when relation evidence is weak or context-dependent."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "left_memory": _memory_review_payload(left),
                            "right_memory": _memory_review_payload(right),
                            "required_json_schema": {
                                "relation_type": "duplicates|conflicts_with|supersedes|none",
                                "confidence": "number 0..1",
                                "source_memory_id": "memory id for relation source; for supersedes this is the newer/canonical memory",
                                "target_memory_id": "memory id for relation target",
                                "reason": "short explanation",
                                "evidence": "object with concise supporting details",
                                "suggested_action": "short action for a human or governance agent to review",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        if self.transport is not None:
            return self.transport(payload)

        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        opener = build_opener(ProxyHandler({}))
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RuntimeError(f"LLM governance request failed: {exc.reason}") from exc

    def _suggestion_from_model(
        self,
        left: MemoryRecordModel,
        right: MemoryRecordModel,
        raw: dict[str, Any],
    ) -> MemoryRelationSuggestion | None:
        content = raw["choices"][0]["message"]["content"]
        data = _parse_json_object(content)
        relation_type = str(data.get("relation_type") or "none")
        if relation_type == "none":
            return None
        if relation_type not in {"duplicates", "conflicts_with", "supersedes"}:
            return None
        confidence = _clamp(float(data.get("confidence", 0)))
        if confidence < self.min_confidence:
            return None
        valid_ids = {left.memory_id, right.memory_id}
        source_memory_id = str(data.get("source_memory_id") or left.memory_id)
        target_memory_id = str(data.get("target_memory_id") or right.memory_id)
        if source_memory_id not in valid_ids or target_memory_id not in valid_ids or source_memory_id == target_memory_id:
            source_memory_id, target_memory_id = left.memory_id, right.memory_id
        evidence = dict(data.get("evidence") or {})
        evidence.update(
            {
                "reviewer": "openai-compatible-governance-reviewer-v1",
                "model": self.model,
                "provider": self.name,
            }
        )
        return MemoryRelationSuggestion(
            suggestion_id=relation_suggestion_id(relation_type, source_memory_id, target_memory_id),
            relation_type=relation_type,
            confidence=confidence,
            source_memory_id=source_memory_id,
            target_memory_id=target_memory_id,
            reason=str(data.get("reason") or "LLM reviewer suggested this governance relation."),
            evidence=evidence,
            suggested_action=str(data.get("suggested_action") or "Review this LLM-assisted governance suggestion."),
        )


def suggest_relation_for_pair(
    db: Session,
    left: MemoryRecordModel,
    right: MemoryRecordModel,
) -> MemoryRelationSuggestion | None:
    return RuleBasedGovernanceReviewer().suggest(db, left, right)


def _rule_suggest_relation_for_pair(
    db: Session,
    left: MemoryRecordModel,
    right: MemoryRecordModel,
) -> MemoryRelationSuggestion | None:
    left_terms = memory_terms(left)
    right_terms = memory_terms(right)
    overlap = jaccard(left_terms, right_terms)
    combined = left_terms | right_terms
    if overlap >= 0.72 and not has_existing_relation(db, left.memory_id, right.memory_id, "duplicates"):
        source, target = (left, right) if left.importance >= right.importance else (right, left)
        return MemoryRelationSuggestion(
            suggestion_id=relation_suggestion_id("duplicates", source.memory_id, target.memory_id),
            relation_type="duplicates",
            confidence=round(min(0.99, overlap), 4),
            source_memory_id=source.memory_id,
            target_memory_id=target.memory_id,
            reason="Active memories have highly overlapping terms and may represent the same reusable knowledge.",
            evidence={"term_overlap": round(overlap, 4), "shared_terms": sorted(left_terms & right_terms)[:12]},
            suggested_action="Create a duplicates relation or merge these memories into one canonical record.",
        )

    supersedes_source, supersedes_target = _rule_supersedes_candidate(left, right, overlap)
    if supersedes_source is not None and supersedes_target is not None and not has_existing_relation(
        db,
        supersedes_source.memory_id,
        supersedes_target.memory_id,
        "supersedes",
    ):
        return MemoryRelationSuggestion(
            suggestion_id=relation_suggestion_id(
                "supersedes",
                supersedes_source.memory_id,
                supersedes_target.memory_id,
            ),
            relation_type="supersedes",
            confidence=round(min(0.92, 0.55 + overlap), 4),
            source_memory_id=supersedes_source.memory_id,
            target_memory_id=supersedes_target.memory_id,
            reason="A newer active memory appears to replace older guidance for the same topic.",
            evidence={
                "term_overlap": round(overlap, 4),
                "shared_terms": sorted(left_terms & right_terms)[:12],
                "source_created_at": supersedes_source.created_at.isoformat() if supersedes_source.created_at else None,
                "target_created_at": supersedes_target.created_at.isoformat() if supersedes_target.created_at else None,
            },
            suggested_action="Create a supersedes relation so retrieval filters the stale memory.",
        )

    conflict_pairs = [
        ("safe", "unsafe"),
        ("safe", "require"),
        ("safe", "requires"),
        ("allow", "requires"),
        ("allow", "require"),
        ("allowed", "requires"),
        ("allowed", "require"),
        ("without", "requires"),
        ("without", "require"),
        ("pass", "failed"),
        ("approved", "blocked"),
    ]
    has_conflict_marker = any(a in combined and b in combined for a, b in conflict_pairs)
    if overlap >= 0.25 and has_conflict_marker and not has_existing_relation(
        db, left.memory_id, right.memory_id, "conflicts_with"
    ):
        source, target = (left, right) if left.created_at >= right.created_at else (right, left)
        return MemoryRelationSuggestion(
            suggestion_id=relation_suggestion_id("conflicts_with", source.memory_id, target.memory_id),
            relation_type="conflicts_with",
            confidence=round(min(0.95, 0.45 + overlap), 4),
            source_memory_id=source.memory_id,
            target_memory_id=target.memory_id,
            reason="Active memories discuss overlapping terms but contain opposing policy or outcome markers.",
            evidence={"term_overlap": round(overlap, 4), "shared_terms": sorted(left_terms & right_terms)[:12]},
            suggested_action="Create a conflicts_with relation and ask a reviewer or agent to resolve the canonical guidance.",
        )
    return None


def _rule_supersedes_candidate(
    left: MemoryRecordModel,
    right: MemoryRecordModel,
    overlap: float,
) -> tuple[MemoryRecordModel | None, MemoryRecordModel | None]:
    if overlap < 0.2:
        return None, None
    newer, older = (left, right) if left.created_at >= right.created_at else (right, left)
    newer_text = f"{newer.summary} {newer.content}".casefold()
    older_text = f"{older.summary} {older.content}".casefold()
    newer_markers = ("updated", "latest", "new guidance", "now ", "requires", "must", "replaces")
    older_markers = ("old guidance", "previous", "initial", "original", "formerly", "without", "allowed")
    if any(marker in newer_text for marker in newer_markers) and any(marker in older_text for marker in older_markers):
        return newer, older
    return None, None


def list_relation_suggestions(
    db: Session,
    task_id: str | None = None,
    limit: int | None = None,
    reviewer_provider: GovernanceReviewerProvider | None = None,
) -> list[MemoryRelationSuggestion]:
    stmt = (
        select(MemoryRecordModel)
        .where(MemoryRecordModel.status == MemoryStatus.active)
        .order_by(MemoryRecordModel.created_at.desc())
        .limit(200)
    )
    if task_id:
        stmt = stmt.where(MemoryRecordModel.task_id == task_id)
    memories = list(db.scalars(stmt))
    suggestions: list[MemoryRelationSuggestion] = []
    seen_suggestion_ids: set[str] = set()
    rule_reviewer = RuleBasedGovernanceReviewer()
    llm_reviewer = reviewer_provider or _configured_llm_reviewer()
    llm_reviewed_pairs = 0
    llm_max_pairs = _configured_llm_max_pairs() if reviewer_provider is None else 500
    for index, left in enumerate(memories):
        for right in memories[index + 1 :]:
            if left.task_id != right.task_id or left.memory_type != right.memory_type or left.scope != right.scope:
                continue
            suggestion = rule_reviewer.suggest(db, left, right)
            if suggestion:
                _append_unique_suggestion(suggestions, seen_suggestion_ids, suggestion)
                continue
            if llm_reviewer is None or llm_reviewed_pairs >= llm_max_pairs or not _should_llm_review_pair(left, right):
                continue
            llm_reviewed_pairs += 1
            suggestion = llm_reviewer.suggest(db, left, right)
            if suggestion:
                _append_unique_suggestion(suggestions, seen_suggestion_ids, suggestion)
    suggestions.sort(key=lambda item: item.confidence, reverse=True)
    if limit is None:
        return suggestions
    return suggestions[: min(limit, 200)]


def create_relation_from_values(
    db: Session,
    *,
    source_memory_id: str,
    target_memory_id: str,
    relation_type: str,
    reason: str,
) -> MemoryRelationModel:
    source = db.get(MemoryRecordModel, source_memory_id)
    target = db.get(MemoryRecordModel, target_memory_id)
    if source is None or target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    relation = MemoryRelationModel(
        source_memory_id=source.memory_id,
        target_memory_id=target.memory_id,
        relation_type=relation_type,
        reason=reason,
    )
    db.add(relation)
    if relation_type == "supersedes" and target.status != MemoryStatus.superseded:
        db.add(
            MemoryStatusDecisionModel(
                memory_id=target.memory_id,
                from_status=target.status,
                to_status=MemoryStatus.superseded,
                reason=f"Superseded by {source.memory_id}: {reason}",
            )
        )
        target.status = MemoryStatus.superseded
    return relation


def accept_suggestion(
    db: Session,
    suggestion: MemoryRelationSuggestion,
    *,
    actor: str,
    reason: str | None = None,
    action_type: str = "accept_relation_suggestion",
) -> tuple[MemoryRelationModel, MemoryGovernanceActionModel]:
    relation = create_relation_from_values(
        db,
        source_memory_id=suggestion.source_memory_id,
        target_memory_id=suggestion.target_memory_id,
        relation_type=suggestion.relation_type,
        reason=reason or suggestion.reason,
    )
    db.flush()
    action = MemoryGovernanceActionModel(
        action_type=action_type,
        actor=actor,
        relation_id=relation.relation_id,
        suggestion_id=suggestion.suggestion_id,
        reason=reason or suggestion.suggested_action,
        evidence=suggestion.model_dump(),
    )
    db.add(action)
    return relation, action


def accept_relation_suggestion_by_id(
    db: Session,
    *,
    suggestion_id: str,
    actor: str,
    reason: str | None = None,
) -> AcceptMemoryRelationSuggestionResponse:
    suggestion = next((item for item in list_relation_suggestions(db) if item.suggestion_id == suggestion_id), None)
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found or no longer valid")
    relation, action = accept_suggestion(db, suggestion, actor=actor, reason=reason)
    db.commit()
    db.refresh(relation)
    db.refresh(action)
    return AcceptMemoryRelationSuggestionResponse(
        relation=memory_relation_to_schema(relation),
        action=memory_governance_action_to_schema(action),
    )


def run_governance(db: Session, payload: RunGovernanceRequest) -> RunGovernanceResponse:
    suggestions = list_relation_suggestions(db)
    duplicate_candidates = [
        suggestion
        for suggestion in suggestions
        if suggestion.relation_type == "duplicates"
        and suggestion.confidence >= payload.duplicate_confidence_threshold
    ]
    conflict_count = sum(1 for suggestion in suggestions if suggestion.relation_type == "conflicts_with")
    accepted_relation_ids: list[str] = []
    accepted_suggestion_ids: list[str] = []

    for suggestion in duplicate_candidates[: payload.max_accepts]:
        relation, _ = accept_suggestion(
            db,
            suggestion,
            actor=payload.actor,
            reason="Governance pass accepted high-confidence duplicate suggestion.",
            action_type="governance_pass_accept_duplicate",
        )
        accepted_relation_ids.append(relation.relation_id)
        accepted_suggestion_ids.append(suggestion.suggestion_id)

    summary_action = MemoryGovernanceActionModel(
        action_type="governance_pass",
        actor=payload.actor,
        relation_id=None,
        suggestion_id=None,
        reason="Ran conservative governance pass.",
        evidence={
            "inspected_suggestions": len(suggestions),
            "accepted_suggestions": len(accepted_relation_ids),
            "skipped_conflicts": conflict_count,
            "duplicate_confidence_threshold": payload.duplicate_confidence_threshold,
            "max_accepts": payload.max_accepts,
            "accepted_suggestion_ids": accepted_suggestion_ids,
            "accepted_relation_ids": accepted_relation_ids,
        },
    )
    db.add(summary_action)
    db.commit()
    db.refresh(summary_action)
    return RunGovernanceResponse(
        inspected_suggestions=len(suggestions),
        accepted_suggestions=len(accepted_relation_ids),
        skipped_conflicts=conflict_count,
        accepted_relation_ids=accepted_relation_ids,
        action=memory_governance_action_to_schema(summary_action),
    )


def list_memory_insights(db: Session, task_id: str | None = None, limit: int = 50) -> list[MemoryInsight]:
    insights: list[MemoryInsight] = []
    relation_stmt = (
        select(MemoryRelationModel)
        .where(MemoryRelationModel.status == "open")
        .order_by(MemoryRelationModel.created_at.desc())
        .limit(200)
    )
    for relation in db.scalars(relation_stmt):
        source = db.get(MemoryRecordModel, relation.source_memory_id)
        target = db.get(MemoryRecordModel, relation.target_memory_id)
        if task_id and task_id not in {source.task_id if source else None, target.task_id if target else None}:
            continue
        insights.append(relation_insight(relation, source))

    trace_stmt = select(RetrievalTraceModel).order_by(RetrievalTraceModel.created_at.desc()).limit(200)
    if task_id:
        trace_stmt = trace_stmt.where(RetrievalTraceModel.task_id == task_id)
    for trace in db.scalars(trace_stmt):
        insights.extend(trace_insights(trace))

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    insights.sort(key=lambda item: (severity_rank.get(item.severity, 9), item.created_at or utcnow()), reverse=False)
    return insights[: min(limit, 200)]


def _append_unique_suggestion(
    suggestions: list[MemoryRelationSuggestion],
    seen_suggestion_ids: set[str],
    suggestion: MemoryRelationSuggestion,
) -> None:
    if suggestion.suggestion_id in seen_suggestion_ids:
        return
    seen_suggestion_ids.add(suggestion.suggestion_id)
    suggestions.append(suggestion)


def _configured_llm_reviewer() -> GovernanceReviewerProvider | None:
    from agentmemos.config import get_settings

    settings = get_settings()
    if settings.governance_reviewer_backend != "openai":
        return None
    return OpenAIGovernanceReviewer(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_governance_model,
        timeout_seconds=settings.openai_governance_timeout_seconds,
        min_confidence=settings.governance_reviewer_min_confidence,
    )


def _configured_llm_max_pairs() -> int:
    from agentmemos.config import get_settings

    return get_settings().governance_reviewer_max_pairs


def _should_llm_review_pair(left: MemoryRecordModel, right: MemoryRecordModel) -> bool:
    overlap = jaccard(memory_terms(left), memory_terms(right))
    if overlap >= 0.12:
        return True
    return left.agent_id != right.agent_id and bool(memory_terms(left) & memory_terms(right))


def _memory_review_payload(memory: MemoryRecordModel) -> dict[str, Any]:
    return {
        "memory_id": memory.memory_id,
        "task_id": memory.task_id,
        "agent_id": memory.agent_id,
        "memory_type": memory.memory_type,
        "scope": memory.scope,
        "summary": memory.summary,
        "content": memory.content,
        "confidence": memory.confidence,
        "importance": memory.importance,
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
    }


def _parse_json_object(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM response did not contain a JSON object")
    return json.loads(cleaned[start : end + 1])


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))
