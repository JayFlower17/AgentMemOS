from uuid import uuid4

from agentmemos.database import SessionLocal, init_db
from agentmemos.enums import AgentRole, EventType, MemoryScope, MemoryStatus, MemoryType
from agentmemos.repositories import EventRepository, GovernanceRepository, MemoryRepository
from agentmemos.schemas import AgentEventCreate, MemoryCreate, PromoteMemoryRequest, UpdateMemoryStatusRequest
from agentmemos.worker import create_memory


def test_event_repository_creates_and_lists_events():
    init_db()
    task_id = f"task_repo_event_{uuid4().hex}"
    with SessionLocal() as db:
        repository = EventRepository(db)
        event = repository.create(
            AgentEventCreate(
                event_type=EventType.task_created,
                task_id=task_id,
                agent_id="planner_1",
                agent_role=AgentRole.planner,
                content="Planner created repository boundary task.",
            )
        )

        events = repository.list_recent(limit=20)

    assert event.task_id == task_id
    assert event.event_id in {item.event_id for item in events}


def test_memory_repository_handles_promotion_and_status_history():
    init_db()
    task_id = f"task_repo_memory_{uuid4().hex}"
    with SessionLocal() as db:
        memory = create_memory(
            db,
            MemoryCreate(
                task_id=task_id,
                agent_id="reviewer_1",
                memory_type=MemoryType.episodic,
                scope=MemoryScope.task_local,
                content="Repository boundary should preserve memory lifecycle history.",
            ),
        )
        repository = MemoryRepository(db)

        repository.promote(
            memory,
            PromoteMemoryRequest(to_scope=MemoryScope.team_shared, reason="Repository test promotion."),
        )
        repository.update_status(
            memory,
            UpdateMemoryStatusRequest(status=MemoryStatus.archived, reason="Repository test archive."),
        )

        refreshed = repository.get(memory.memory_id)
        promotions = repository.list_promotions_for_memory(memory.memory_id)
        status_decisions = repository.list_status_decisions_for_memory(memory.memory_id)

    assert refreshed is not None
    assert refreshed.scope == MemoryScope.team_shared
    assert refreshed.status == MemoryStatus.archived
    assert promotions[0].to_scope == MemoryScope.team_shared
    assert status_decisions[0].to_status == MemoryStatus.archived


def test_governance_repository_lists_relations_for_memory():
    init_db()
    task_id = f"task_repo_governance_{uuid4().hex}"
    with SessionLocal() as db:
        first = create_memory(
            db,
            MemoryCreate(
                task_id=task_id,
                agent_id="reviewer_1",
                memory_type=MemoryType.episodic,
                scope=MemoryScope.team_shared,
                content="Repository relation source memory.",
            ),
        )
        second = create_memory(
            db,
            MemoryCreate(
                task_id=task_id,
                agent_id="reviewer_2",
                memory_type=MemoryType.episodic,
                scope=MemoryScope.team_shared,
                content="Repository relation target memory.",
            ),
        )
        from agentmemos.governance import create_relation_from_values

        relation = create_relation_from_values(
            db,
            source_memory_id=first.memory_id,
            target_memory_id=second.memory_id,
            relation_type="duplicates",
            reason="Repository test relation.",
        )
        db.commit()
        db.refresh(relation)

        repository = GovernanceRepository(db)
        relations = repository.list_relations_for_memory(first.memory_id)
        resolved = repository.resolve_relation(relation, "Repository test resolution.")

    assert relation.relation_id in {item.relation_id for item in relations}
    assert resolved.status == "resolved"
    assert "Resolution: Repository test resolution." in resolved.reason
