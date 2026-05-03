import asyncio
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class JobType(StrEnum):
    extract_memory = "extract_memory"
    embed_memory = "embed_memory"
    governance_pass = "governance_pass"


@dataclass(frozen=True)
class MemoryJob:
    job_type: JobType
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({"job_type": self.job_type.value, "payload": self.payload}, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str | bytes) -> "MemoryJob":
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return cls(JobType(data["job_type"]), dict(data.get("payload") or {}))

    @classmethod
    def extract_memory(cls, event_id: str) -> "MemoryJob":
        return cls(JobType.extract_memory, {"event_id": event_id})

    @classmethod
    def embed_memory(cls, memory_id: str) -> "MemoryJob":
        return cls(JobType.embed_memory, {"memory_id": memory_id})

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


class RedisJobQueue:
    def __init__(self, *, redis_url: str, queue_name: str = "agentmemos:jobs") -> None:
        try:
            from redis import Redis
        except ImportError as exc:
            raise RuntimeError("RedisJobQueue requires installing the optional 'redis' dependency.") from exc
        self.redis_url = redis_url
        self.queue_name = queue_name
        self._redis = Redis.from_url(redis_url)

    async def enqueue(self, job: MemoryJob) -> None:
        await asyncio.to_thread(self._redis.rpush, self.queue_name, job.to_json())

    async def dequeue(self) -> MemoryJob:
        _, raw = await asyncio.to_thread(self._redis.blpop, self.queue_name)
        return MemoryJob.from_json(raw)

    def task_done(self) -> None:
        return None

    async def join(self) -> None:
        return None


def create_job_queue(*, backend: str = "memory", redis_url: str = "", redis_queue_name: str = "agentmemos:jobs") -> JobQueue:
    if backend == "memory":
        return InMemoryJobQueue()
    if backend == "redis":
        return RedisJobQueue(redis_url=redis_url, queue_name=redis_queue_name)
    raise ValueError(f"Unsupported job queue backend: {backend}")
