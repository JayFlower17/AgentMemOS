from agentmemos.enums import AgentRole, EventType, MemoryScope, MemoryType
from agentmemos.models import AgentEventModel
from agentmemos.schemas import MemoryCreate


def summarize(text: str, max_chars: int = 140) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 1].rstrip() + "..."


def classify_event(event: AgentEventModel) -> tuple[MemoryType, MemoryScope, float, float]:
    if event.event_type == EventType.task_created:
        return MemoryType.working, MemoryScope.task_local, 0.85, 0.8
    if event.event_type == EventType.review_finding_created:
        return MemoryType.episodic, MemoryScope.team_shared, 0.86, 0.9
    if event.event_type == EventType.subtask_completed:
        return MemoryType.working, MemoryScope.task_local, 0.82, 0.75
    if event.event_type == EventType.task_completed:
        return MemoryType.procedural, MemoryScope.team_shared, 0.78, 0.85
    if event.event_type == EventType.tool_result_observed:
        scope = MemoryScope.agent_local if event.agent_role == AgentRole.coder else MemoryScope.task_local
        return MemoryType.episodic, scope, 0.72, 0.65
    return MemoryType.working, MemoryScope.agent_local, 0.65, 0.45


def extract_memory(event: AgentEventModel) -> MemoryCreate | None:
    if not event.content.strip():
        return None
    memory_type, scope, confidence, importance = classify_event(event)
    return MemoryCreate(
        task_id=event.task_id,
        agent_id=event.agent_id,
        memory_type=memory_type,
        scope=scope,
        content=event.content,
        summary=summarize(event.content),
        confidence=confidence,
        importance=importance,
        source_event_id=event.event_id,
    )
