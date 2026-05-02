from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentmemos.config import get_settings
from agentmemos.database import get_db, init_db
from agentmemos.enums import MemoryStatus
from agentmemos.models import (
    AgentEventModel,
    MemoryDecisionTraceModel,
    MemoryRelationModel,
    MemoryRecordModel,
    MemoryStatusDecisionModel,
    PromotionDecisionModel,
    RetrievalTraceModel,
    new_id,
    utcnow,
)
from agentmemos.retrieval import pack_context, retrieve_memories
from agentmemos.schemas import (
    AgentEvent,
    AgentEventCreate,
    DashboardStats,
    HealthResponse,
    MemoryCreate,
    MemoryDecisionTrace,
    MemoryRelation,
    MemoryRelationCreate,
    MemoryRelationResolveRequest,
    MemoryRecord,
    MemoryStatusDecision,
    PromotionDecision,
    PromoteMemoryRequest,
    RetrievalTrace,
    RetrieveRequest,
    RetrieveResponse,
    UpdateMemoryStatusRequest,
)
from agentmemos.serializers import (
    event_to_schema,
    memory_decision_to_schema,
    memory_relation_to_schema,
    memory_to_schema,
    promotion_to_schema,
    status_decision_to_schema,
    trace_to_schema,
)
from agentmemos.worker import MemoryWorker, create_memory


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    worker = MemoryWorker()
    await worker.start()
    app.state.memory_worker = worker
    try:
        yield
    finally:
        await worker.stop()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name)


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/events", response_model=AgentEvent, status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(request: Request, payload: AgentEventCreate, db: Session = Depends(get_db)) -> AgentEvent:
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
    db.add(event)
    db.commit()
    db.refresh(event)
    await request.app.state.memory_worker.enqueue(event.event_id)
    return event_to_schema(event)


@app.post("/memories", response_model=MemoryRecord, status_code=status.HTTP_201_CREATED)
def create_memory_endpoint(payload: MemoryCreate, db: Session = Depends(get_db)) -> MemoryRecord:
    return memory_to_schema(create_memory(db, payload))


@app.get("/events", response_model=list[AgentEvent])
def list_events(limit: int = 50, db: Session = Depends(get_db)) -> list[AgentEvent]:
    stmt = select(AgentEventModel).order_by(AgentEventModel.created_at.desc()).limit(min(limit, 200))
    return [event_to_schema(event) for event in db.scalars(stmt)]


@app.get("/memories", response_model=list[MemoryRecord])
def list_memories(
    task_id: str | None = None,
    scope: str | None = None,
    memory_type: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[MemoryRecord]:
    stmt = select(MemoryRecordModel).order_by(MemoryRecordModel.created_at.desc()).limit(min(limit, 300))
    if task_id:
        stmt = stmt.where(MemoryRecordModel.task_id == task_id)
    if scope:
        stmt = stmt.where(MemoryRecordModel.scope == scope)
    if memory_type:
        stmt = stmt.where(MemoryRecordModel.memory_type == memory_type)
    return [memory_to_schema(memory) for memory in db.scalars(stmt)]


@app.get("/memories/{memory_id}", response_model=MemoryRecord)
def get_memory(memory_id: str, db: Session = Depends(get_db)) -> MemoryRecord:
    memory = db.get(MemoryRecordModel, memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return memory_to_schema(memory)


@app.get("/memories/{memory_id}/decisions", response_model=list[MemoryDecisionTrace])
def list_memory_decisions(memory_id: str, db: Session = Depends(get_db)) -> list[MemoryDecisionTrace]:
    memory = db.get(MemoryRecordModel, memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    stmt = (
        select(MemoryDecisionTraceModel)
        .where(MemoryDecisionTraceModel.memory_id == memory_id)
        .order_by(MemoryDecisionTraceModel.created_at.desc())
    )
    return [memory_decision_to_schema(decision) for decision in db.scalars(stmt)]


@app.get("/memories/{memory_id}/promotions", response_model=list[PromotionDecision])
def list_memory_promotions(memory_id: str, db: Session = Depends(get_db)) -> list[PromotionDecision]:
    memory = db.get(MemoryRecordModel, memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    stmt = (
        select(PromotionDecisionModel)
        .where(PromotionDecisionModel.memory_id == memory_id)
        .order_by(PromotionDecisionModel.created_at.desc())
    )
    return [promotion_to_schema(decision) for decision in db.scalars(stmt)]


@app.get("/memories/{memory_id}/status-decisions", response_model=list[MemoryStatusDecision])
def list_memory_status_decisions(memory_id: str, db: Session = Depends(get_db)) -> list[MemoryStatusDecision]:
    memory = db.get(MemoryRecordModel, memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    stmt = (
        select(MemoryStatusDecisionModel)
        .where(MemoryStatusDecisionModel.memory_id == memory_id)
        .order_by(MemoryStatusDecisionModel.created_at.desc())
    )
    return [status_decision_to_schema(decision) for decision in db.scalars(stmt)]


@app.get("/memory-decisions", response_model=list[MemoryDecisionTrace])
def list_memory_decision_traces(limit: int = 50, db: Session = Depends(get_db)) -> list[MemoryDecisionTrace]:
    stmt = select(MemoryDecisionTraceModel).order_by(MemoryDecisionTraceModel.created_at.desc()).limit(min(limit, 200))
    return [memory_decision_to_schema(decision) for decision in db.scalars(stmt)]


@app.get("/promotions", response_model=list[PromotionDecision])
def list_promotions(limit: int = 50, db: Session = Depends(get_db)) -> list[PromotionDecision]:
    stmt = select(PromotionDecisionModel).order_by(PromotionDecisionModel.created_at.desc()).limit(min(limit, 200))
    return [promotion_to_schema(decision) for decision in db.scalars(stmt)]


@app.get("/traces", response_model=list[RetrievalTrace])
def list_traces(limit: int = 50, db: Session = Depends(get_db)) -> list[RetrievalTrace]:
    stmt = select(RetrievalTraceModel).order_by(RetrievalTraceModel.created_at.desc()).limit(min(limit, 200))
    return [trace_to_schema(trace) for trace in db.scalars(stmt)]


@app.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)) -> DashboardStats:
    def grouped_counts(model, column) -> dict[str, int]:
        rows = db.execute(select(column, func.count()).select_from(model).group_by(column)).all()
        return {str(key): count for key, count in rows}

    return DashboardStats(
        total_events=db.scalar(select(func.count()).select_from(AgentEventModel)) or 0,
        total_memories=db.scalar(select(func.count()).select_from(MemoryRecordModel)) or 0,
        total_traces=db.scalar(select(func.count()).select_from(RetrievalTraceModel)) or 0,
        total_promotions=db.scalar(select(func.count()).select_from(PromotionDecisionModel)) or 0,
        total_relations=db.scalar(select(func.count()).select_from(MemoryRelationModel)) or 0,
        open_relations=db.scalar(
            select(func.count()).select_from(MemoryRelationModel).where(MemoryRelationModel.status == "open")
        )
        or 0,
        active_memories=db.scalar(
            select(func.count()).select_from(MemoryRecordModel).where(MemoryRecordModel.status == MemoryStatus.active)
        )
        or 0,
        scope_counts=grouped_counts(MemoryRecordModel, MemoryRecordModel.scope),
        type_counts=grouped_counts(MemoryRecordModel, MemoryRecordModel.memory_type),
        status_counts=grouped_counts(MemoryRecordModel, MemoryRecordModel.status),
        role_counts=grouped_counts(AgentEventModel, AgentEventModel.agent_role),
    )


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(payload: RetrieveRequest, db: Session = Depends(get_db)) -> RetrieveResponse:
    memories, trace = retrieve_memories(db, payload)
    return RetrieveResponse(
        trace_id=trace.trace_id,
        memories=[memory_to_schema(memory) for memory in memories],
        packed_context=pack_context(memories),
    )


@app.post("/memories/{memory_id}/promote", response_model=MemoryRecord)
def promote_memory(memory_id: str, payload: PromoteMemoryRequest, db: Session = Depends(get_db)) -> MemoryRecord:
    memory = db.get(MemoryRecordModel, memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    decision = PromotionDecisionModel(
        memory_id=memory.memory_id,
        from_scope=memory.scope,
        to_scope=payload.to_scope,
        reason=payload.reason,
    )
    memory.scope = payload.to_scope
    db.add(decision)
    db.commit()
    db.refresh(memory)
    return memory_to_schema(memory)


@app.post("/memory-relations", response_model=MemoryRelation, status_code=status.HTTP_201_CREATED)
def create_memory_relation(payload: MemoryRelationCreate, db: Session = Depends(get_db)) -> MemoryRelation:
    if payload.source_memory_id == payload.target_memory_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A memory cannot relate to itself")
    source = db.get(MemoryRecordModel, payload.source_memory_id)
    target = db.get(MemoryRecordModel, payload.target_memory_id)
    if source is None or target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")

    relation = MemoryRelationModel(
        source_memory_id=source.memory_id,
        target_memory_id=target.memory_id,
        relation_type=payload.relation_type,
        reason=payload.reason,
    )
    db.add(relation)
    if payload.relation_type == "supersedes" and target.status != MemoryStatus.superseded:
        db.add(
            MemoryStatusDecisionModel(
                memory_id=target.memory_id,
                from_status=target.status,
                to_status=MemoryStatus.superseded,
                reason=f"Superseded by {source.memory_id}: {payload.reason}",
            )
        )
        target.status = MemoryStatus.superseded
    db.commit()
    db.refresh(relation)
    return memory_relation_to_schema(relation)


@app.get("/memory-relations", response_model=list[MemoryRelation])
def list_memory_relations(
    status_filter: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[MemoryRelation]:
    stmt = select(MemoryRelationModel).order_by(MemoryRelationModel.created_at.desc()).limit(min(limit, 200))
    if status_filter:
        stmt = stmt.where(MemoryRelationModel.status == status_filter)
    return [memory_relation_to_schema(relation) for relation in db.scalars(stmt)]


@app.get("/memories/{memory_id}/relations", response_model=list[MemoryRelation])
def list_memory_relations_for_memory(memory_id: str, db: Session = Depends(get_db)) -> list[MemoryRelation]:
    memory = db.get(MemoryRecordModel, memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    stmt = (
        select(MemoryRelationModel)
        .where(
            (MemoryRelationModel.source_memory_id == memory_id)
            | (MemoryRelationModel.target_memory_id == memory_id)
        )
        .order_by(MemoryRelationModel.created_at.desc())
    )
    return [memory_relation_to_schema(relation) for relation in db.scalars(stmt)]


@app.post("/memory-relations/{relation_id}/resolve", response_model=MemoryRelation)
def resolve_memory_relation(
    relation_id: str,
    payload: MemoryRelationResolveRequest,
    db: Session = Depends(get_db),
) -> MemoryRelation:
    relation = db.get(MemoryRelationModel, relation_id)
    if relation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relation not found")
    relation.status = "resolved"
    relation.reason = f"{relation.reason}\nResolution: {payload.reason}"
    relation.resolved_at = utcnow()
    db.commit()
    db.refresh(relation)
    return memory_relation_to_schema(relation)


@app.post("/memories/{memory_id}/status", response_model=MemoryRecord)
def update_memory_status(
    memory_id: str, payload: UpdateMemoryStatusRequest, db: Session = Depends(get_db)
) -> MemoryRecord:
    memory = db.get(MemoryRecordModel, memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    decision = MemoryStatusDecisionModel(
        memory_id=memory.memory_id,
        from_status=memory.status,
        to_status=payload.status,
        reason=payload.reason,
    )
    memory.status = payload.status
    db.add(decision)
    db.commit()
    db.refresh(memory)
    return memory_to_schema(memory)


@app.get("/traces/{trace_id}", response_model=RetrievalTrace)
def get_trace(trace_id: str, db: Session = Depends(get_db)) -> RetrievalTrace:
    trace = db.get(RetrievalTraceModel, trace_id)
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")
    return trace_to_schema(trace)
