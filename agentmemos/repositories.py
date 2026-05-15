from sqlalchemy import select
from sqlalchemy.orm import Session

from agentmemos.models import (
    AgentEventModel,
    MemoryDecisionTraceModel,
    MemoryGovernanceActionModel,
    MemoryRecordModel,
    MemoryRelationModel,
    MemoryStatusDecisionModel,
    PromotionDecisionModel,
    RetrievalTraceModel,
    new_id,
    utcnow,
)
from agentmemos.schemas import AgentEventCreate, PromoteMemoryRequest, UpdateMemoryStatusRequest


def _limit(value: int, maximum: int) -> int:
    return min(value, maximum)


class EventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payload: AgentEventCreate) -> AgentEventModel:
        event = AgentEventModel(
            event_id=payload.event_id or new_id("evt"),
            event_type=payload.event_type,
            task_id=payload.task_id,
            agent_id=payload.agent_id,
            agent_role=payload.agent_role,
            content=payload.content,
            event_metadata=payload.metadata,
            created_at=payload.created_at,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_recent(self, *, limit: int = 50) -> list[AgentEventModel]:
        stmt = select(AgentEventModel).order_by(AgentEventModel.created_at.desc()).limit(_limit(limit, 200))
        return list(self.db.scalars(stmt))


class MemoryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, memory_id: str) -> MemoryRecordModel | None:
        return self.db.get(MemoryRecordModel, memory_id)

    def list_recent(
        self,
        *,
        task_id: str | None = None,
        scope: str | None = None,
        memory_type: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecordModel]:
        stmt = select(MemoryRecordModel).order_by(MemoryRecordModel.created_at.desc()).limit(_limit(limit, 10000))
        if task_id:
            stmt = stmt.where(MemoryRecordModel.task_id == task_id)
        if scope:
            stmt = stmt.where(MemoryRecordModel.scope == scope)
        if memory_type:
            stmt = stmt.where(MemoryRecordModel.memory_type == memory_type)
        return list(self.db.scalars(stmt))

    def list_decisions_for_memory(self, memory_id: str) -> list[MemoryDecisionTraceModel]:
        stmt = (
            select(MemoryDecisionTraceModel)
            .where(MemoryDecisionTraceModel.memory_id == memory_id)
            .order_by(MemoryDecisionTraceModel.created_at.desc())
        )
        return list(self.db.scalars(stmt))

    def list_recent_decisions(self, *, limit: int = 50) -> list[MemoryDecisionTraceModel]:
        stmt = (
            select(MemoryDecisionTraceModel)
            .order_by(MemoryDecisionTraceModel.created_at.desc())
            .limit(_limit(limit, 200))
        )
        return list(self.db.scalars(stmt))

    def list_promotions_for_memory(self, memory_id: str) -> list[PromotionDecisionModel]:
        stmt = (
            select(PromotionDecisionModel)
            .where(PromotionDecisionModel.memory_id == memory_id)
            .order_by(PromotionDecisionModel.created_at.desc())
        )
        return list(self.db.scalars(stmt))

    def list_recent_promotions(self, *, limit: int = 50) -> list[PromotionDecisionModel]:
        stmt = (
            select(PromotionDecisionModel)
            .order_by(PromotionDecisionModel.created_at.desc())
            .limit(_limit(limit, 200))
        )
        return list(self.db.scalars(stmt))

    def list_status_decisions_for_memory(self, memory_id: str) -> list[MemoryStatusDecisionModel]:
        stmt = (
            select(MemoryStatusDecisionModel)
            .where(MemoryStatusDecisionModel.memory_id == memory_id)
            .order_by(MemoryStatusDecisionModel.created_at.desc())
        )
        return list(self.db.scalars(stmt))

    def promote(self, memory: MemoryRecordModel, payload: PromoteMemoryRequest) -> MemoryRecordModel:
        decision = PromotionDecisionModel(
            memory_id=memory.memory_id,
            from_scope=memory.scope,
            to_scope=payload.to_scope,
            reason=payload.reason,
        )
        memory.scope = payload.to_scope
        self.db.add(decision)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def update_status(self, memory: MemoryRecordModel, payload: UpdateMemoryStatusRequest) -> MemoryRecordModel:
        decision = MemoryStatusDecisionModel(
            memory_id=memory.memory_id,
            from_status=memory.status,
            to_status=payload.status,
            reason=payload.reason,
        )
        memory.status = payload.status
        self.db.add(decision)
        self.db.commit()
        self.db.refresh(memory)
        return memory


class TraceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, trace_id: str) -> RetrievalTraceModel | None:
        return self.db.get(RetrievalTraceModel, trace_id)

    def list_recent(self, *, limit: int = 50) -> list[RetrievalTraceModel]:
        stmt = select(RetrievalTraceModel).order_by(RetrievalTraceModel.created_at.desc()).limit(_limit(limit, 200))
        return list(self.db.scalars(stmt))


class GovernanceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_relation(self, relation_id: str) -> MemoryRelationModel | None:
        return self.db.get(MemoryRelationModel, relation_id)

    def list_recent_relations(
        self,
        *,
        status_filter: str | None = None,
        limit: int = 50,
    ) -> list[MemoryRelationModel]:
        stmt = select(MemoryRelationModel).order_by(MemoryRelationModel.created_at.desc()).limit(_limit(limit, 200))
        if status_filter:
            stmt = stmt.where(MemoryRelationModel.status == status_filter)
        return list(self.db.scalars(stmt))

    def list_relations_for_memory(self, memory_id: str) -> list[MemoryRelationModel]:
        stmt = (
            select(MemoryRelationModel)
            .where(
                (MemoryRelationModel.source_memory_id == memory_id)
                | (MemoryRelationModel.target_memory_id == memory_id)
            )
            .order_by(MemoryRelationModel.created_at.desc())
        )
        return list(self.db.scalars(stmt))

    def resolve_relation(self, relation: MemoryRelationModel, reason: str) -> MemoryRelationModel:
        relation.status = "resolved"
        relation.reason = f"{relation.reason}\nResolution: {reason}"
        relation.resolved_at = utcnow()
        self.db.commit()
        self.db.refresh(relation)
        return relation

    def list_recent_actions(self, *, limit: int = 50) -> list[MemoryGovernanceActionModel]:
        stmt = (
            select(MemoryGovernanceActionModel)
            .order_by(MemoryGovernanceActionModel.created_at.desc())
            .limit(_limit(limit, 200))
        )
        return list(self.db.scalars(stmt))
