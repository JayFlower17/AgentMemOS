from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentmemos.enums import AgentRole, EventType, MemoryScope, MemoryStatus, MemoryType


class AgentEventCreate(BaseModel):
    event_id: str | None = None
    event_type: EventType
    task_id: str
    agent_id: str
    agent_role: AgentRole
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class AgentEvent(BaseModel):
    event_id: str
    event_type: EventType
    task_id: str
    agent_id: str
    agent_role: AgentRole
    content: str
    metadata: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemoryCreate(BaseModel):
    task_id: str | None = None
    agent_id: str | None = None
    memory_type: MemoryType
    scope: MemoryScope
    content: str = Field(min_length=1)
    summary: str | None = None
    confidence: float = Field(default=0.75, ge=0, le=1)
    importance: float = Field(default=0.5, ge=0, le=1)
    source_event_id: str | None = None


class MemoryRecord(BaseModel):
    memory_id: str
    task_id: str | None
    agent_id: str | None
    memory_type: MemoryType
    scope: MemoryScope
    content: str
    summary: str
    confidence: float
    importance: float
    source_event_id: str | None
    status: MemoryStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemoryDecisionTrace(BaseModel):
    decision_id: str
    memory_id: str
    source_event_id: str | None
    decision_type: str
    chosen_memory_type: MemoryType
    chosen_scope: MemoryScope
    confidence: float
    importance: float
    reason: str
    signals: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PromoteMemoryRequest(BaseModel):
    to_scope: MemoryScope
    reason: str = Field(min_length=1)


class UpdateMemoryStatusRequest(BaseModel):
    status: MemoryStatus
    reason: str = Field(min_length=1)


class MemoryStatusDecision(BaseModel):
    decision_id: str
    memory_id: str
    from_status: MemoryStatus
    to_status: MemoryStatus
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemoryRelationCreate(BaseModel):
    source_memory_id: str
    target_memory_id: str
    relation_type: str = Field(pattern="^(supersedes|conflicts_with|duplicates)$")
    reason: str = Field(min_length=1)


class MemoryRelationResolveRequest(BaseModel):
    reason: str = Field(default="Relation has been reviewed.")


class MemoryRelation(BaseModel):
    relation_id: str
    source_memory_id: str
    target_memory_id: str
    relation_type: str
    status: str
    reason: str
    created_at: datetime
    resolved_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class PromotionDecision(BaseModel):
    decision_id: str
    memory_id: str
    from_scope: MemoryScope
    to_scope: MemoryScope
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RetrieveRequest(BaseModel):
    task_id: str
    agent_id: str
    agent_role: AgentRole
    query: str = Field(min_length=1)
    allowed_scopes: list[MemoryScope] = Field(default_factory=lambda: [
        MemoryScope.task_local,
        MemoryScope.team_shared,
        MemoryScope.project_global,
    ])
    limit: int = Field(default=8, ge=1, le=30)


class RetrievalTrace(BaseModel):
    trace_id: str
    task_id: str
    agent_id: str
    agent_role: AgentRole
    query: str
    searched_scopes: list[MemoryScope]
    selected_memories: list[str]
    filtered_memories: list[str]
    scored_memories: list[dict[str, Any]] = Field(default_factory=list)
    filter_reasons: dict[str, str] = Field(default_factory=dict)
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RetrieveResponse(BaseModel):
    trace_id: str
    memories: list[MemoryRecord]
    packed_context: str


class HealthResponse(BaseModel):
    status: str
    service: str


class DashboardStats(BaseModel):
    total_events: int
    total_memories: int
    total_traces: int
    active_memories: int
    total_promotions: int
    total_relations: int
    open_relations: int
    scope_counts: dict[str, int]
    type_counts: dict[str, int]
    status_counts: dict[str, int]
    role_counts: dict[str, int]
