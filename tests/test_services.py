import asyncio
from uuid import uuid4

from agentmemos.database import SessionLocal, init_db
from agentmemos.enums import AgentRole, EventType, MemoryScope, MemoryStatus, MemoryType
from agentmemos.governance import create_relation_from_values
from agentmemos.queue import InMemoryJobQueue, JobType
from agentmemos.repositories import EventRepository, GovernanceRepository, MemoryRepository
from agentmemos.schemas import (
    AgentEventCreate,
    MemoryCreate,
    MemoryRelationResolveRequest,
    PromoteMemoryRequest,
    UpdateMemoryStatusRequest,
)
from agentmemos.services import EventIngestionService, GovernanceRelationService, MemoryLifecycleService
from agentmemos.worker import create_memory


def test_event_ingestion_service_creates_event_and_enqueues_extraction_job():
    init_db()
    task_id = f"task_service_event_{uuid4().hex}"

    async def run_service():
        queue = InMemoryJobQueue()
        with SessionLocal() as db:
            service = EventIngestionService(EventRepository(db), queue)
            event = await service.ingest(
                AgentEventCreate(
                    event_type=EventType.review_finding_created,
                    task_id=task_id,
                    agent_id="reviewer_1",
                    agent_role=AgentRole.reviewer,
                    content="Reviewer found a service-layer extraction event.",
                )
            )
            job = await queue.dequeue()
            queue.task_done()
            await queue.join()
            return event, job

    event, job = asyncio.run(run_service())

    assert event.task_id == task_id
    assert job.job_type == JobType.extract_memory
    assert job.payload["event_id"] == event.event_id


def test_memory_lifecycle_service_promotes_and_archives_memory():
    init_db()
    task_id = f"task_service_memory_{uuid4().hex}"
    with SessionLocal() as db:
        memory = create_memory(
            db,
            MemoryCreate(
                task_id=task_id,
                agent_id="reviewer_1",
                memory_type=MemoryType.episodic,
                scope=MemoryScope.task_local,
                content="Service layer should orchestrate memory lifecycle changes.",
            ),
        )
        service = MemoryLifecycleService(MemoryRepository(db))

        promoted = service.promote(
            memory.memory_id,
            PromoteMemoryRequest(to_scope=MemoryScope.team_shared, reason="Service test promotion."),
        )
        archived = service.update_status(
            memory.memory_id,
            UpdateMemoryStatusRequest(status=MemoryStatus.archived, reason="Service test archive."),
        )

    assert promoted is not None
    assert archived is not None
    assert promoted.scope == MemoryScope.team_shared
    assert archived.status == MemoryStatus.archived


def test_governance_relation_service_resolves_relation():
    init_db()
    task_id = f"task_service_relation_{uuid4().hex}"
    with SessionLocal() as db:
        first = create_memory(
            db,
            MemoryCreate(
                task_id=task_id,
                agent_id="reviewer_1",
                memory_type=MemoryType.episodic,
                scope=MemoryScope.team_shared,
                content="Service relation source memory.",
            ),
        )
        second = create_memory(
            db,
            MemoryCreate(
                task_id=task_id,
                agent_id="reviewer_2",
                memory_type=MemoryType.episodic,
                scope=MemoryScope.team_shared,
                content="Service relation target memory.",
            ),
        )
        relation = create_relation_from_values(
            db,
            source_memory_id=first.memory_id,
            target_memory_id=second.memory_id,
            relation_type="duplicates",
            reason="Service test relation.",
        )
        db.commit()
        db.refresh(relation)

        resolved = GovernanceRelationService(GovernanceRepository(db)).resolve_relation(
            relation.relation_id,
            MemoryRelationResolveRequest(reason="Service test resolution."),
        )

    assert resolved is not None
    assert resolved.status == "resolved"
    assert "Service test resolution." in resolved.reason
