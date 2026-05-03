import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class JobType(StrEnum):
    extract_memory = "extract_memory"
    governance_pass = "governance_pass"


@dataclass(frozen=True)
class MemoryJob:
    job_type: JobType
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def extract_memory(cls, event_id: str) -> "MemoryJob":
        return cls(JobType.extract_memory, {"event_id": event_id})

    @classmethod
    def governance_pass(
        cls,
        *,
        actor: str,
        duplicate_confidence_threshold: float,
        max_accepts: int,
    ) -> "MemoryJob":
        return cls(
            JobType.governance_pass,
            {
                "actor": actor,
                "duplicate_confidence_threshold": duplicate_confidence_threshold,
                "max_accepts": max_accepts,
            },
        )


class JobQueue(Protocol):
    async def enqueue(self, job: MemoryJob) -> None: ...

    async def dequeue(self) -> MemoryJob: ...

    def task_done(self) -> None: ...

    async def join(self) -> None: ...


class InMemoryJobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[MemoryJob] = asyncio.Queue()

    async def enqueue(self, job: MemoryJob) -> None:
        await self._queue.put(job)

    async def dequeue(self) -> MemoryJob:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()
