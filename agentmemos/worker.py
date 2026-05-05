import asyncio
from contextlib import suppress

from sqlalchemy.orm import Session
from sqlalchemy import select

from agentmemos.config import get_settings
from agentmemos.database import SessionLocal
from agentmemos.event_bus import MemoryEventBus
from agentmemos.extractor import ExtractorProvider, create_extractor_provider
from agentmemos.governance import run_governance
from agentmemos.models import AgentEventModel, MemoryDecisionTraceModel, MemoryRecordModel
from agentmemos.queue import InMemoryJobQueue, JobQueue, JobType, MemoryJob
from agentmemos.schemas import RunGovernanceRequest
from agentmemos.vector import (
    EmbeddingProvider,
    InMemoryVectorStore,
    VectorStore,
    create_embedding_provider,
    memory_embedding_text,
)


class MemoryWorker:
    def __init__(
        self,
        job_queue: JobQueue | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        event_bus: MemoryEventBus | None = None,
        extractor_provider: ExtractorProvider | None = None,
    ) -> None:
        self.settings = get_settings()
        self.job_queue = job_queue or InMemoryJobQueue()
        self.embedding_provider = embedding_provider or create_embedding_provider(provider=self.settings.embedding_provider)
        self.vector_store = vector_store or InMemoryVectorStore()
        self.event_bus = event_bus
        self.extractor_provider = extractor_provider
        self._tasks: list[asyncio.Task] = []
        self._running = False
        if self.extractor_provider is None:
            self.extractor_provider = create_extractor_provider(backend=self.settings.extractor_backend)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tasks = [
            asyncio.create_task(self._run(worker_index=index), name=f"agentmemos-worker-{index}")
            for index in range(self.settings.worker_concurrency)
        ]

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks = []

    async def enqueue(self, event_id: str) -> None:
        await self.enqueue_job(MemoryJob.extract_memory(event_id))

    async def enqueue_job(self, job: MemoryJob) -> None:
        job = job.with_retry_policy(
            max_attempts=self.settings.job_max_attempts,
            backoff_seconds=self.settings.job_retry_backoff_seconds,
        )
        await self.job_queue.enqueue(job)
        self._publish("job.enqueued", {"job_type": job.job_type.value, "payload": job.payload})

    async def drain(self) -> None:
        await self.job_queue.join()

    def state(self) -> dict:
        return {
            "running": self._running,
            "worker_concurrency": self.settings.worker_concurrency,
            "active_workers": len([task for task in self._tasks if not task.done()]),
            "queue": self.job_queue.stats(),
            "max_attempts": self.settings.job_max_attempts,
            "retry_backoff_seconds": self.settings.job_retry_backoff_seconds,
        }

    async def _run(self, *, worker_index: int = 0) -> None:
        while self._running:
            job = await self.job_queue.dequeue()
            try:
                self._publish(
                    "job.started",
                    {"job_type": job.job_type.value, "payload": job.payload, "worker_index": worker_index},
                )
                await self._process_job(job)
                self._publish(
                    "job.completed",
                    {"job_type": job.job_type.value, "payload": job.payload, "worker_index": worker_index},
                )
            except Exception as exc:
                retried = await self._handle_failure(job, exc)
                self._publish(
                    "job.failed",
                    {
                        "job_type": job.job_type.value,
                        "payload": job.payload,
                        "error": str(exc),
                        "attempts": job.attempts + 1,
                        "max_attempts": job.max_attempts,
                        "will_retry": retried,
                        "worker_index": worker_index,
                    },
                )
            finally:
                self.job_queue.task_done()

    async def _process_job(self, job: MemoryJob) -> None:
        if job.job_type == JobType.extract_memory:
            if self.settings.extraction_delay_seconds:
                await asyncio.sleep(self.settings.extraction_delay_seconds)
            event_id = str(job.payload.get("event_id") or "")
            if event_id:
                memory = await asyncio.to_thread(self._process_event, event_id)
                if memory is not None:
                    self._publish(
                        "memory.extracted",
                        {
                            "memory_id": memory.memory_id,
                            "event_id": event_id,
                            "task_id": memory.task_id,
                            "scope": memory.scope,
                            "memory_type": memory.memory_type,
                        },
                    )
                    await self.enqueue_job(MemoryJob.embed_memory(memory.memory_id))
            return
        if job.job_type == JobType.embed_memory:
            memory_id = str(job.payload.get("memory_id") or "")
            if memory_id:
                embedded = await asyncio.to_thread(self._process_embedding, memory_id)
                if embedded:
                    self._publish("memory.embedded", {"memory_id": memory_id})
            return
        if job.job_type == JobType.governance_pass:
            summary = await asyncio.to_thread(self._process_governance_pass, job)
            self._publish(
                "governance.completed",
                {
                    "actor": summary.action.actor,
                    "accepted_suggestions": summary.accepted_suggestions,
                    "accepted_relation_ids": summary.accepted_relation_ids,
                },
            )

    def _process_event(self, event_id: str) -> MemoryRecordModel | None:
        with SessionLocal() as db:
            event = db.get(AgentEventModel, event_id)
            if event is None:
                return None
            result = self.extractor_provider.extract(event)
            if not result.should_write or result.memory is None:
                return None
            return create_memory(
                db,
                result.memory,
                decision_type="extracted",
                decision_reason=result.reason,
                decision_signals=result.signals,
            )

    def _process_embedding(self, memory_id: str) -> bool:
        with SessionLocal() as db:
            memory = db.get(MemoryRecordModel, memory_id)
            if memory is None:
                return False
            embedding = self.embedding_provider.embed(memory_embedding_text(memory))
            self.vector_store.upsert(memory.memory_id, embedding)
            return True

    def _process_governance_pass(self, job: MemoryJob):
        payload = RunGovernanceRequest(
            actor=str(job.payload.get("actor") or "governance_worker"),
            duplicate_confidence_threshold=float(job.payload.get("duplicate_confidence_threshold") or 0.85),
            max_accepts=int(job.payload.get("max_accepts") or 10),
        )
        with SessionLocal() as db:
            return run_governance(db, payload)

    def _publish(self, event_type: str, payload: dict | None = None) -> None:
        if self.event_bus is not None:
            self.event_bus.publish(event_type, payload)

    async def _handle_failure(self, job: MemoryJob, exc: Exception) -> bool:
        if job.can_retry:
            retry_job = job.next_attempt()
            if retry_job.backoff_seconds:
                await asyncio.sleep(retry_job.backoff_seconds)
            await self.job_queue.enqueue(retry_job)
            self._publish(
                "job.retried",
                {
                    "job_type": retry_job.job_type.value,
                    "payload": retry_job.payload,
                    "attempts": retry_job.attempts,
                    "max_attempts": retry_job.max_attempts,
                },
            )
            return True
        await self.job_queue.fail(job, error=str(exc))
        self._publish(
            "job.dead_lettered",
            {
                "job_type": job.job_type.value,
                "payload": job.payload,
                "attempts": job.attempts + 1,
                "max_attempts": job.max_attempts,
                "error": str(exc),
            },
        )
        return False


def create_memory(
    db: Session,
    memory,
    *,
    decision_type: str = "manual",
    decision_reason: str | None = None,
    decision_signals: dict | None = None,
) -> MemoryRecordModel:
    if memory.source_event_id:
        existing = db.scalar(
            select(MemoryRecordModel).where(MemoryRecordModel.source_event_id == memory.source_event_id)
        )
        if existing is not None:
            return existing

    duplicate = _find_duplicate_memory(db, memory)
    if duplicate is not None:
        _record_memory_decision(
            db,
            duplicate,
            decision_type="deduplicated",
            decision_reason="Duplicate memory content was merged into an existing memory record instead of creating a new one.",
            decision_signals={
                "source": decision_type,
                "dedup_strategy": "exact-normalized-content",
                "duplicate_source_event_id": memory.source_event_id or "manual",
                "original_reason": decision_reason or "Memory was created explicitly through the API.",
            },
            source_event_id=memory.source_event_id,
        )
        return duplicate

    record = MemoryRecordModel(
        task_id=memory.task_id,
        agent_id=memory.agent_id,
        memory_type=memory.memory_type,
        scope=memory.scope,
        content=memory.content,
        summary=memory.summary or memory.content[:140],
        confidence=memory.confidence,
        importance=memory.importance,
        source_event_id=memory.source_event_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    _record_memory_decision(
        db,
        record,
        decision_type=decision_type,
        decision_reason=decision_reason or "Memory was created explicitly through the API.",
        decision_signals=decision_signals or {"source": decision_type},
    )
    return record


def _normalize_content(content: str) -> str:
    return " ".join(content.casefold().split())


def _find_duplicate_memory(db: Session, memory) -> MemoryRecordModel | None:
    target_content = _normalize_content(memory.content)
    candidates = db.scalars(
        select(MemoryRecordModel).where(
            MemoryRecordModel.task_id == memory.task_id,
            MemoryRecordModel.agent_id == memory.agent_id,
            MemoryRecordModel.memory_type == memory.memory_type,
            MemoryRecordModel.scope == memory.scope,
            MemoryRecordModel.status == "active",
        )
    )
    return next(
        (candidate for candidate in candidates if _normalize_content(candidate.content) == target_content),
        None,
    )


def _record_memory_decision(
    db: Session,
    record: MemoryRecordModel,
    *,
    decision_type: str,
    decision_reason: str,
    decision_signals: dict,
    source_event_id: str | None = None,
) -> None:
    decision = MemoryDecisionTraceModel(
        memory_id=record.memory_id,
        source_event_id=source_event_id if source_event_id is not None else record.source_event_id,
        decision_type=decision_type,
        chosen_memory_type=record.memory_type,
        chosen_scope=record.scope,
        confidence=record.confidence,
        importance=record.importance,
        reason=decision_reason,
        signals=decision_signals,
    )
    db.add(decision)
    db.commit()
