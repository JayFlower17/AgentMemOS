from agentmemos.models import AgentEventModel, MemoryRecordModel, PromotionDecisionModel, RetrievalTraceModel
from agentmemos.schemas import AgentEvent, MemoryRecord, PromotionDecision, RetrievalTrace


def event_to_schema(model: AgentEventModel) -> AgentEvent:
    return AgentEvent(
        event_id=model.event_id,
        event_type=model.event_type,
        task_id=model.task_id,
        agent_id=model.agent_id,
        agent_role=model.agent_role,
        content=model.content,
        metadata=model.event_metadata or {},
        created_at=model.created_at,
    )


def memory_to_schema(model: MemoryRecordModel) -> MemoryRecord:
    return MemoryRecord.model_validate(model)


def trace_to_schema(model: RetrievalTraceModel) -> RetrievalTrace:
    return RetrievalTrace.model_validate(model)


def promotion_to_schema(model: PromotionDecisionModel) -> PromotionDecision:
    return PromotionDecision.model_validate(model)
