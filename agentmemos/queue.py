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
    attempts: int = 0
    max_attempts: int = 3
    backoff_seconds: float = 1.0

    def to_json(self) -> str:
        return json.dumps(
            {
                "job_type": self.job_type.value,
                "payload": self.payload,
                "attempts": self.attempts,
                "max_attempts": self.max_attempts,
                "backoff_seconds": self.backoff_seconds,
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> "MemoryJob":
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return cls(
            JobType(data["job_type"]),
            dict(data.get("payload") or {}),
            attempts=int(data.get("attempts", 0)),
            max_attempts=int(data.get("max_attempts", 3)),
            backoff_seconds=float(data.get("backoff_seconds", 1.0)),
        )

    def with_retry_policy(self, *, max_attempts: int, backoff_seconds: float) -> "MemoryJob":
        return MemoryJob(
            self.job_type,
            dict(self.payload),
            attempts=self.attempts,
            max_attempts=max_attempts,
            backoff_seconds=backoff_seconds,
        )

    def next_attempt(self) -> "MemoryJob":
        return MemoryJob(
            self.job_type,
            dict(self.payload),
            attempts=self.attempts + 1,
            max_attempts=self.max_attempts,
            backoff_seconds=self.backoff_seconds,
        )

    @property
    def can_retry(self) -> bool:
        return self.attempts + 1 < self.max_attempts

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

    def stats(self) -> dict[str, Any]: ...

    async def fail(self, job: MemoryJob, *, error: str) -> None: ...


class InMemoryJobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[MemoryJob] = asyncio.Queue()
        self.enqueued = 0
        self.dequeued = 0
        self.completed = 0
        self.failed = 0
        self.dead_lettered = 0
        self.last_error: str | None = None
        self._dead_letters: list[dict[str, Any]] = []

    async def enqueue(self, job: MemoryJob) -> None:
        self.enqueued += 1
        await self._queue.put(job)

    async def dequeue(self) -> MemoryJob:
        job = await self._queue.get()
        self.dequeued += 1
        return job

    def task_done(self) -> None:
        self.completed += 1
        self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "memory",
            "queue_name": "memory",
            "pending": self._queue.qsize(),
            "dead_lettered": self.dead_lettered,
            "enqueued": self.enqueued,
            "dequeued": self.dequeued,
            "completed": self.completed,
            "failed": self.failed,
            "last_error": self.last_error,
        }

    async def fail(self, job: MemoryJob, *, error: str) -> None:
        self.failed += 1
        self.dead_lettered += 1
        self.last_error = error
        self._dead_letters.append({"job": job.to_json(), "error": error})


class RedisJobQueue:
    def __init__(self, *, redis_url: str, queue_name: str = "agentmemos:jobs") -> None:
        try:
            from redis import Redis
        except ImportError as exc:
            raise RuntimeError("RedisJobQueue requires installing the optional 'redis' dependency.") from exc
        self.redis_url = redis_url
        self.queue_name = queue_name
        self.dead_letter_queue_name = f"{queue_name}:dead"
        self.stats_key = f"{queue_name}:stats"
        self._redis = Redis.from_url(redis_url)

    async def enqueue(self, job: MemoryJob) -> None:
        await asyncio.to_thread(self._enqueue_sync, job)

    async def dequeue(self) -> MemoryJob:
        _, raw = await asyncio.to_thread(self._redis.blpop, self.queue_name)
        await asyncio.to_thread(self._redis.hincrby, self.stats_key, "dequeued", 1)
        return MemoryJob.from_json(raw)

    async def join(self) -> None:
        return None

    def stats(self) -> dict[str, Any]:
        raw = self._redis.hgetall(self.stats_key)
        counters = {}
        for key, value in raw.items():
            decoded_key = key.decode("utf-8") if isinstance(key, bytes) else str(key)
            try:
                counters[decoded_key] = int(value)
            except (TypeError, ValueError):
                continue
        return {
            "backend": "redis",
            "queue_name": self.queue_name,
            "pending": self._redis.llen(self.queue_name),
            "dead_lettered": self._redis.llen(self.dead_letter_queue_name),
            "enqueued": counters.get("enqueued", 0),
            "dequeued": counters.get("dequeued", 0),
            "completed": counters.get("completed", 0),
            "failed": counters.get("failed", 0),
            "last_error": self._decode(self._redis.hget(self.stats_key, "last_error")),
        }

    async def fail(self, job: MemoryJob, *, error: str) -> None:
        await asyncio.to_thread(self._fail_sync, job, error)

    def task_done(self) -> None:
        self._redis.hincrby(self.stats_key, "completed", 1)

    def _enqueue_sync(self, job: MemoryJob) -> None:
        self._redis.rpush(self.queue_name, job.to_json())
        self._redis.hincrby(self.stats_key, "enqueued", 1)

    def _fail_sync(self, job: MemoryJob, error: str) -> None:
        self._redis.rpush(
            self.dead_letter_queue_name,
            json.dumps({"job": json.loads(job.to_json()), "error": error}, separators=(",", ":")),
        )
        self._redis.hincrby(self.stats_key, "failed", 1)
        self._redis.hset(self.stats_key, "last_error", error)

    def _decode(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)


def create_job_queue(*, backend: str = "memory", redis_url: str = "", redis_queue_name: str = "agentmemos:jobs") -> JobQueue:
    if backend == "memory":
        return InMemoryJobQueue()
    if backend == "redis":
        return RedisJobQueue(redis_url=redis_url, queue_name=redis_queue_name)
    raise ValueError(f"Unsupported job queue backend: {backend}")
