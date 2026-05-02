from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from agentmemos.enums import AgentRole, MemoryScope, MemoryStatus, MemoryType
from agentmemos.models import MemoryRecordModel, RetrievalTraceModel
from agentmemos.schemas import RetrieveRequest


ROLE_TYPE_WEIGHTS = {
    AgentRole.planner: {MemoryType.working: 1.0, MemoryType.episodic: 0.5, MemoryType.procedural: 0.7},
    AgentRole.coder: {MemoryType.working: 0.8, MemoryType.episodic: 0.8, MemoryType.procedural: 1.0},
    AgentRole.reviewer: {MemoryType.working: 0.6, MemoryType.episodic: 1.0, MemoryType.procedural: 0.8},
}

SCOPE_WEIGHTS = {
    MemoryScope.agent_local: 0.45,
    MemoryScope.task_local: 0.75,
    MemoryScope.team_shared: 1.0,
    MemoryScope.project_global: 0.9,
}


def _keyword_score(query: str, memory: MemoryRecordModel) -> float:
    terms = {term.lower() for term in query.split() if len(term) > 2}
    if not terms:
        return 0.0
    haystack = f"{memory.summary} {memory.content}".lower()
    hits = sum(1 for term in terms if term in haystack)
    return hits / len(terms)


def _score_memory(req: RetrieveRequest, memory: MemoryRecordModel) -> tuple[float, dict[str, float]]:
    type_weights = ROLE_TYPE_WEIGHTS[req.agent_role]
    parts = {
        "importance": memory.importance * 0.35,
        "confidence": memory.confidence * 0.25,
        "scope": SCOPE_WEIGHTS[MemoryScope(memory.scope)] * 0.2,
        "role_type": type_weights[MemoryType(memory.memory_type)] * 0.12,
        "keyword": _keyword_score(req.query, memory) * 0.08,
    }
    return sum(parts.values()), parts


def _is_visible(req: RetrieveRequest, memory: MemoryRecordModel) -> tuple[bool, str | None]:
    scope = MemoryScope(memory.scope)
    if scope == MemoryScope.agent_local and memory.agent_id != req.agent_id:
        return False, "Filtered another agent's local memory."
    if scope != MemoryScope.project_global and memory.task_id != req.task_id:
        return False, "Filtered memory from another task."
    return True, None


def retrieve_memories(db: Session, req: RetrieveRequest) -> tuple[list[MemoryRecordModel], RetrievalTraceModel]:
    allowed = [scope.value for scope in req.allowed_scopes]
    stmt = (
        select(MemoryRecordModel)
        .where(MemoryRecordModel.status == MemoryStatus.active)
        .where(MemoryRecordModel.scope.in_(allowed))
        .where(or_(MemoryRecordModel.task_id == req.task_id, MemoryRecordModel.scope == MemoryScope.project_global))
    )
    candidates = list(db.scalars(stmt))

    filtered: list[str] = []
    scored: list[tuple[float, MemoryRecordModel]] = []
    filter_reasons: dict[str, str] = {}
    scored_memories: list[dict] = []
    reasons: list[str] = []

    for memory in candidates:
        visible, reason = _is_visible(req, memory)
        if not visible:
            filtered.append(memory.memory_id)
            if reason:
                filter_reasons[memory.memory_id] = reason
            if reason and reason not in reasons:
                reasons.append(reason)
            continue
        score, parts = _score_memory(req, memory)
        scored.append((score, memory))
        scored_memories.append(
            {
                "memory_id": memory.memory_id,
                "score": round(score, 4),
                "selected": False,
                "scope": memory.scope,
                "memory_type": memory.memory_type,
                "score_parts": {key: round(value, 4) for key, value in parts.items()},
            }
        )

    selected = [memory for _, memory in sorted(scored, key=lambda item: item[0], reverse=True)[: req.limit]]
    selected_ids = {memory.memory_id for memory in selected}
    scored_memories = sorted(scored_memories, key=lambda item: item["score"], reverse=True)
    for item in scored_memories:
        item["selected"] = item["memory_id"] in selected_ids
    reason = "Selected memories by scope visibility, role/type affinity, confidence, importance, and keyword overlap."
    if reasons:
        reason = f"{reason} {' '.join(reasons)}"

    trace = RetrievalTraceModel(
        task_id=req.task_id,
        agent_id=req.agent_id,
        agent_role=req.agent_role,
        query=req.query,
        searched_scopes=[scope.value for scope in req.allowed_scopes],
        selected_memories=[memory.memory_id for memory in selected],
        filtered_memories=filtered,
        scored_memories=scored_memories,
        filter_reasons=filter_reasons,
        reason=reason,
    )
    db.add(trace)
    db.commit()
    db.refresh(trace)
    return selected, trace


def pack_context(memories: list[MemoryRecordModel]) -> str:
    if not memories:
        return ""
    lines = []
    for memory in memories:
        lines.append(f"- [{memory.scope}/{memory.memory_type}] {memory.summary}")
    return "\n".join(lines)
