from agentmemos.queue import MemoryJob, JobQueue
from agentmemos.repositories import EventRepository, GovernanceRepository, MemoryRepository
from agentmemos.event_bus import MemoryEventBus
from agentmemos.schemas import (
    AgentEventCreate,
    MemoryRelationResolveRequest,
    PromoteMemoryRequest,
    UpdateMemoryStatusRequest,
)
from agentmemos.models import AgentEventModel, MemoryRecordModel, MemoryRelationModel


class EventIngestionService:
    def __init__(
        self,
        event_repository: EventRepository,
        job_queue: JobQueue,
        event_bus: MemoryEventBus | None = None,
        *,
        job_max_attempts: int = 3,
        job_retry_backoff_seconds: float = 1.0,
    ) -> None:
        self.event_repository = event_repository
        self.job_queue = job_queue
        self.event_bus = event_bus
        self.job_max_attempts = job_max_attempts
        self.job_retry_backoff_seconds = job_retry_backoff_seconds

    async def ingest(self, payload: AgentEventCreate) -> AgentEventModel:
        event = self.event_repository.create(payload)
        job = MemoryJob.extract_memory(event.event_id).with_retry_policy(
            max_attempts=self.job_max_attempts,
            backoff_seconds=self.job_retry_backoff_seconds,
        )
        await self.job_queue.enqueue(job)
        if self.event_bus is not None:
            self.event_bus.publish("job.enqueued", {"job_type": job.job_type.value, "payload": job.payload})
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
