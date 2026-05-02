import asyncio
from contextlib import suppress

from sqlalchemy.orm import Session
from sqlalchemy import select

from agentmemos.config import get_settings
from agentmemos.database import SessionLocal
from agentmemos.extractor import extract_memory
from agentmemos.models import AgentEventModel, MemoryRecordModel


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
            create_memory(db, memory)


def create_memory(db: Session, memory) -> MemoryRecordModel:
    if memory.source_event_id:
        existing = db.scalar(
            select(MemoryRecordModel).where(MemoryRecordModel.source_event_id == memory.source_event_id)
        )
        if existing is not None:
            return existing

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
    return record
