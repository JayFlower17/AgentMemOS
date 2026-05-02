from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from agentmemos.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


class AgentEventModel(Base):
    __tablename__ = "agent_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("evt"))
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    task_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_role: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class MemoryRecordModel(Base):
    __tablename__ = "memory_records"

    memory_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("mem"))
    task_id: Mapped[str | None] = mapped_column(String(128), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(128), index=True)
    memory_type: Mapped[str] = mapped_column(String(32), index=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    source_event_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("agent_events.event_id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RetrievalTraceModel(Base):
    __tablename__ = "retrieval_traces"

    trace_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("trace"))
    task_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_role: Mapped[str] = mapped_column(String(32), index=True)
    query: Mapped[str] = mapped_column(Text)
    searched_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    selected_memories: Mapped[list[str]] = mapped_column(JSON, default=list)
    filtered_memories: Mapped[list[str]] = mapped_column(JSON, default=list)
    scored_memories: Mapped[list[dict]] = mapped_column(JSON, default=list)
    filter_reasons: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class MemoryDecisionTraceModel(Base):
    __tablename__ = "memory_decision_traces"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("mdec"))
    memory_id: Mapped[str] = mapped_column(String(64), ForeignKey("memory_records.memory_id"), index=True)
    source_event_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("agent_events.event_id"), nullable=True, index=True
    )
    decision_type: Mapped[str] = mapped_column(String(32), index=True)
    chosen_memory_type: Mapped[str] = mapped_column(String(32))
    chosen_scope: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    importance: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    signals: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class PromotionDecisionModel(Base):
    __tablename__ = "promotion_decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("promo"))
    memory_id: Mapped[str] = mapped_column(String(64), ForeignKey("memory_records.memory_id"), index=True)
    from_scope: Mapped[str] = mapped_column(String(32))
    to_scope: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryStatusDecisionModel(Base):
    __tablename__ = "memory_status_decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("status"))
    memory_id: Mapped[str] = mapped_column(String(64), ForeignKey("memory_records.memory_id"), index=True)
    from_status: Mapped[str] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryRelationModel(Base):
    __tablename__ = "memory_relations"

    relation_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("rel"))
    source_memory_id: Mapped[str] = mapped_column(String(64), ForeignKey("memory_records.memory_id"), index=True)
    target_memory_id: Mapped[str] = mapped_column(String(64), ForeignKey("memory_records.memory_id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index("ix_memory_task_scope_status", MemoryRecordModel.task_id, MemoryRecordModel.scope, MemoryRecordModel.status)
