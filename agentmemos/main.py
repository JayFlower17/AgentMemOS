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
from agentmemos.governance import (
    accept_relation_suggestion_by_id,
    create_relation_from_values,
    list_memory_insights as build_memory_insights,
    list_relation_suggestions,
    run_governance,
)
from agentmemos.jobs import GovernanceScheduler
from agentmemos.models import (
    AgentEventModel,
    MemoryRelationModel,
    MemoryRecordModel,
    PromotionDecisionModel,
    RetrievalTraceModel,
)
from agentmemos.queue import MemoryJob, create_job_queue
from agentmemos.repositories import EventRepository, GovernanceRepository, MemoryRepository, TraceRepository
from agentmemos.retrieval import pack_context, retrieve_memories
from agentmemos.schemas import (
    AcceptMemoryRelationSuggestionRequest,
    AcceptMemoryRelationSuggestionResponse,
    AgentEvent,
    AgentEventCreate,
    DashboardStats,
    GovernanceSchedulerStatus,
    HealthResponse,
    MemoryCreate,
    MemoryDecisionTrace,
    MemoryGovernanceAction,
    MemoryInsight,
    MemoryRelation,
    MemoryRelationCreate,
    MemoryRelationResolveRequest,
    MemoryRelationSuggestion,
    MemoryRecord,
    MemoryStatusDecision,
    PromotionDecision,
    PromoteMemoryRequest,
    RetrievalTrace,
    RetrieveRequest,
    RetrieveResponse,
    RunGovernanceRequest,
    RunGovernanceResponse,
    UpdateMemoryStatusRequest,
)
from agentmemos.serializers import (
    event_to_schema,
    memory_decision_to_schema,
    memory_governance_action_to_schema,
    memory_relation_to_schema,
    memory_to_schema,
    promotion_to_schema,
    status_decision_to_schema,
    trace_to_schema,
)
from agentmemos.services import EventIngestionService, GovernanceRelationService, MemoryLifecycleService
from agentmemos.vector import create_vector_store
from agentmemos.worker import MemoryWorker, create_memory


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    job_queue = create_job_queue(
        backend=settings.job_queue_backend,
        redis_url=settings.redis_url,
        redis_queue_name=settings.redis_queue_name,
    )
    vector_store = create_vector_store(backend=settings.vector_store_backend)
    worker = MemoryWorker(job_queue=job_queue, vector_store=vector_store)
    await worker.start()
    governance_scheduler = GovernanceScheduler(job_queue=worker.job_queue)
    await governance_scheduler.start()
    app.state.memory_worker = worker
    app.state.governance_scheduler = governance_scheduler
    try:
        yield
    finally:
        await governance_scheduler.stop()
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
    service = EventIngestionService(EventRepository(db), request.app.state.memory_worker.job_queue)
    event = await service.ingest(payload)
    return event_to_schema(event)


@app.post("/memories", response_model=MemoryRecord, status_code=status.HTTP_201_CREATED)
async def create_memory_endpoint(request: Request, payload: MemoryCreate, db: Session = Depends(get_db)) -> MemoryRecord:
    memory = create_memory(db, payload)
    await request.app.state.memory_worker.enqueue_job(MemoryJob.embed_memory(memory.memory_id))
    return memory_to_schema(memory)


@app.get("/events", response_model=list[AgentEvent])
def list_events(limit: int = 50, db: Session = Depends(get_db)) -> list[AgentEvent]:
    return [event_to_schema(event) for event in EventRepository(db).list_recent(limit=limit)]


@app.get("/memories", response_model=list[MemoryRecord])
def list_memories(
    task_id: str | None = None,
    scope: str | None = None,
    memory_type: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[MemoryRecord]:
    memories = MemoryRepository(db).list_recent(task_id=task_id, scope=scope, memory_type=memory_type, limit=limit)
    return [memory_to_schema(memory) for memory in memories]


@app.get("/memories/{memory_id}", response_model=MemoryRecord)
def get_memory(memory_id: str, db: Session = Depends(get_db)) -> MemoryRecord:
    memory = MemoryRepository(db).get(memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return memory_to_schema(memory)


@app.get("/memories/{memory_id}/decisions", response_model=list[MemoryDecisionTrace])
def list_memory_decisions(memory_id: str, db: Session = Depends(get_db)) -> list[MemoryDecisionTrace]:
    repository = MemoryRepository(db)
    memory = repository.get(memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return [memory_decision_to_schema(decision) for decision in repository.list_decisions_for_memory(memory_id)]


@app.get("/memories/{memory_id}/promotions", response_model=list[PromotionDecision])
def list_memory_promotions(memory_id: str, db: Session = Depends(get_db)) -> list[PromotionDecision]:
    repository = MemoryRepository(db)
    memory = repository.get(memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return [promotion_to_schema(decision) for decision in repository.list_promotions_for_memory(memory_id)]


@app.get("/memories/{memory_id}/status-decisions", response_model=list[MemoryStatusDecision])
def list_memory_status_decisions(memory_id: str, db: Session = Depends(get_db)) -> list[MemoryStatusDecision]:
    repository = MemoryRepository(db)
    memory = repository.get(memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return [status_decision_to_schema(decision) for decision in repository.list_status_decisions_for_memory(memory_id)]


@app.get("/memory-decisions", response_model=list[MemoryDecisionTrace])
def list_memory_decision_traces(limit: int = 50, db: Session = Depends(get_db)) -> list[MemoryDecisionTrace]:
    return [memory_decision_to_schema(decision) for decision in MemoryRepository(db).list_recent_decisions(limit=limit)]


@app.get("/promotions", response_model=list[PromotionDecision])
def list_promotions(limit: int = 50, db: Session = Depends(get_db)) -> list[PromotionDecision]:
    return [promotion_to_schema(decision) for decision in MemoryRepository(db).list_recent_promotions(limit=limit)]


@app.get("/traces", response_model=list[RetrievalTrace])
def list_traces(limit: int = 50, db: Session = Depends(get_db)) -> list[RetrievalTrace]:
    return [trace_to_schema(trace) for trace in TraceRepository(db).list_recent(limit=limit)]


@app.get("/memory-relation-suggestions", response_model=list[MemoryRelationSuggestion])
def list_memory_relation_suggestions(
    task_id: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[MemoryRelationSuggestion]:
    return list_relation_suggestions(db, task_id=task_id, limit=limit)


@app.post(
    "/memory-relation-suggestions/{suggestion_id}/accept",
    response_model=AcceptMemoryRelationSuggestionResponse,
)
def accept_memory_relation_suggestion(
    suggestion_id: str,
    payload: AcceptMemoryRelationSuggestionRequest,
    db: Session = Depends(get_db),
) -> AcceptMemoryRelationSuggestionResponse:
    return accept_relation_suggestion_by_id(
        db,
        suggestion_id=suggestion_id,
        actor=payload.actor,
        reason=payload.reason,
    )


@app.post("/governance/run", response_model=RunGovernanceResponse)
def run_governance_pass(payload: RunGovernanceRequest, db: Session = Depends(get_db)) -> RunGovernanceResponse:
    return run_governance(db, payload)


@app.get("/governance/scheduler", response_model=GovernanceSchedulerStatus)
def get_governance_scheduler_status(request: Request) -> GovernanceSchedulerStatus:
    return GovernanceSchedulerStatus(**request.app.state.governance_scheduler.state())


@app.get("/memory-governance-actions", response_model=list[MemoryGovernanceAction])
def list_memory_governance_actions(limit: int = 50, db: Session = Depends(get_db)) -> list[MemoryGovernanceAction]:
    return [
        memory_governance_action_to_schema(action)
        for action in GovernanceRepository(db).list_recent_actions(limit=limit)
    ]


@app.get("/memory-insights", response_model=list[MemoryInsight])
def list_memory_insights(
    task_id: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[MemoryInsight]:
    return build_memory_insights(db, task_id=task_id, limit=limit)


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
def retrieve(request: Request, payload: RetrieveRequest, db: Session = Depends(get_db)) -> RetrieveResponse:
    embedding_scores = None
    if settings.vector_retrieval_enabled and settings.vector_retrieval_weight > 0:
        worker = request.app.state.memory_worker
        query_embedding = worker.embedding_provider.embed(payload.query)
        candidate_ids = [memory.memory_id for memory in MemoryRepository(db).list_recent(task_id=payload.task_id, limit=300)]
        embedding_scores = worker.vector_store.search(query_embedding, candidate_ids=candidate_ids, limit=300)
    memories, trace = retrieve_memories(
        db,
        payload,
        embedding_scores=embedding_scores,
        embedding_weight=settings.vector_retrieval_weight,
    )
    return RetrieveResponse(
        trace_id=trace.trace_id,
        memories=[memory_to_schema(memory) for memory in memories],
        packed_context=pack_context(memories),
    )


@app.post("/memories/{memory_id}/promote", response_model=MemoryRecord)
def promote_memory(memory_id: str, payload: PromoteMemoryRequest, db: Session = Depends(get_db)) -> MemoryRecord:
    memory = MemoryLifecycleService(MemoryRepository(db)).promote(memory_id, payload)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return memory_to_schema(memory)


@app.post("/memory-relations", response_model=MemoryRelation, status_code=status.HTTP_201_CREATED)
def create_memory_relation(payload: MemoryRelationCreate, db: Session = Depends(get_db)) -> MemoryRelation:
    if payload.source_memory_id == payload.target_memory_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A memory cannot relate to itself")
    relation = create_relation_from_values(
        db,
        source_memory_id=payload.source_memory_id,
        target_memory_id=payload.target_memory_id,
        relation_type=payload.relation_type,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(relation)
    return memory_relation_to_schema(relation)


@app.get("/memory-relations", response_model=list[MemoryRelation])
def list_memory_relations(
    status_filter: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[MemoryRelation]:
    relations = GovernanceRepository(db).list_recent_relations(status_filter=status_filter, limit=limit)
    return [memory_relation_to_schema(relation) for relation in relations]


@app.get("/memories/{memory_id}/relations", response_model=list[MemoryRelation])
def list_memory_relations_for_memory(memory_id: str, db: Session = Depends(get_db)) -> list[MemoryRelation]:
    memory = MemoryRepository(db).get(memory_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return [
        memory_relation_to_schema(relation)
        for relation in GovernanceRepository(db).list_relations_for_memory(memory_id)
    ]


@app.post("/memory-relations/{relation_id}/resolve", response_model=MemoryRelation)
def resolve_memory_relation(
    relation_id: str,
    payload: MemoryRelationResolveRequest,
    db: Session = Depends(get_db),
) -> MemoryRelation:
    relation = GovernanceRelationService(GovernanceRepository(db)).resolve_relation(relation_id, payload)
    if relation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relation not found")
    return memory_relation_to_schema(relation)


@app.post("/memories/{memory_id}/status", response_model=MemoryRecord)
def update_memory_status(
    memory_id: str, payload: UpdateMemoryStatusRequest, db: Session = Depends(get_db)
) -> MemoryRecord:
    memory = MemoryLifecycleService(MemoryRepository(db)).update_status(memory_id, payload)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return memory_to_schema(memory)


@app.get("/traces/{trace_id}", response_model=RetrievalTrace)
def get_trace(trace_id: str, db: Session = Depends(get_db)) -> RetrievalTrace:
    trace = TraceRepository(db).get(trace_id)
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")
    return trace_to_schema(trace)
