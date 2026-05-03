from agentmemos.queue import MemoryJob, JobQueue
from agentmemos.repositories import EventRepository, GovernanceRepository, MemoryRepository
from agentmemos.schemas import (
    AgentEventCreate,
    MemoryRelationResolveRequest,
    PromoteMemoryRequest,
    UpdateMemoryStatusRequest,
)
from agentmemos.models import AgentEventModel, MemoryRecordModel, MemoryRelationModel


class EventIngestionService:
    def __init__(self, event_repository: EventRepository, job_queue: JobQueue) -> None:
        self.event_repository = event_repository
        self.job_queue = job_queue

    async def ingest(self, payload: AgentEventCreate) -> AgentEventModel:
        event = self.event_repository.create(payload)
        await self.job_queue.enqueue(MemoryJob.extract_memory(event.event_id))
        return event


class MemoryLifecycleService:
    def __init__(self, memory_repository: MemoryRepository) -> None:
        self.memory_repository = memory_repository

    def promote(self, memory_id: str, payload: PromoteMemoryRequest) -> MemoryRecordModel | None:
        memory = self.memory_repository.get(memory_id)
        if memory is None:
            return None
        return self.memory_repository.promote(memory, payload)

    def update_status(self, memory_id: str, payload: UpdateMemoryStatusRequest) -> MemoryRecordModel | None:
        memory = self.memory_repository.get(memory_id)
        if memory is None:
            return None
        return self.memory_repository.update_status(memory, payload)


class GovernanceRelationService:
    def __init__(self, governance_repository: GovernanceRepository) -> None:
        self.governance_repository = governance_repository

    def resolve_relation(
        self,
        relation_id: str,
        payload: MemoryRelationResolveRequest,
    ) -> MemoryRelationModel | None:
        relation = self.governance_repository.get_relation(relation_id)
        if relation is None:
            return None
        return self.governance_repository.resolve_relation(relation, payload.reason)
