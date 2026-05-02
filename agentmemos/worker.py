import asyncio
from contextlib import suppress

from sqlalchemy.orm import Session
from sqlalchemy import select

from agentmemos.config import get_settings
from agentmemos.database import SessionLocal
from agentmemos.extractor import explain_extraction, extract_memory
from agentmemos.models import AgentEventModel, MemoryDecisionTraceModel, MemoryRecordModel


class MemoryWorker:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._running = False
        self.settings = get_settings()

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def enqueue(self, event_id: str) -> None:
        await self.queue.put(event_id)

    async def drain(self) -> None:
        await self.queue.join()

    async def _run(self) -> None:
        while self._running:
            event_id = await self.queue.get()
            try:
                if self.settings.extraction_delay_seconds:
                    await asyncio.sleep(self.settings.extraction_delay_seconds)
                await asyncio.to_thread(self._process_event, event_id)
            finally:
                self.queue.task_done()

    def _process_event(self, event_id: str) -> None:
        with SessionLocal() as db:
            event = db.get(AgentEventModel, event_id)
            if event is None:
                return
            memory = extract_memory(event)
            if memory is None:
                return
            reason, signals = explain_extraction(event, memory)
            create_memory(db, memory, decision_type="extracted", decision_reason=reason, decision_signals=signals)


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
