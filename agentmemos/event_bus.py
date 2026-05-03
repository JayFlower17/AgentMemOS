from __future__ import annotations

import asyncio
import json
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import count
from typing import Any, AsyncIterator


@dataclass(frozen=True)
class MemoryEvent:
    event_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: str
    origin_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "created_at": self.created_at,
            "origin_id": self.origin_id,
        }

    def to_sse(self) -> str:
        data = json.dumps(self.to_dict(), ensure_ascii=False)
        return f"id: {self.event_id}\nevent: {self.event_type}\ndata: {data}\n\n"

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str | bytes) -> "MemoryEvent":
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            payload=dict(data.get("payload") or {}),
            created_at=data["created_at"],
            origin_id=str(data.get("origin_id") or ""),
        )


class RedisEventPublisher:
    def __init__(self, *, redis_url: str, channel: str) -> None:
        try:
            from redis import Redis
        except ImportError as exc:
            raise RuntimeError("Redis event fanout requires installing the optional 'redis' dependency.") from exc
        self.redis_url = redis_url
        self.channel = channel
        self._redis = Redis.from_url(redis_url)

    def publish(self, event: MemoryEvent) -> None:
        self._redis.publish(self.channel, event.to_json())


class RedisEventSubscriber:
    def __init__(self, *, redis_url: str, channel: str) -> None:
        try:
            from redis import Redis
        except ImportError as exc:
            raise RuntimeError("Redis event fanout requires installing the optional 'redis' dependency.") from exc
        self.redis_url = redis_url
        self.channel = channel
        self._redis = Redis.from_url(redis_url)
        self._pubsub = None

    def listen(self):
        self._pubsub = self._redis.pubsub()
        self._pubsub.subscribe(self.channel)
        for message in self._pubsub.listen():
            if message.get("type") == "message":
                yield MemoryEvent.from_json(message["data"])

    def close(self) -> None:
        if self._pubsub is not None:
            self._pubsub.close()


@dataclass
class MemoryEventBus:
    history_size: int = 100
    origin_id: str = field(default_factory=lambda: f"bus_{uuid.uuid4().hex}")
    publisher: RedisEventPublisher | None = None
    _events: deque[MemoryEvent] = field(default_factory=deque, init=False)
    _subscribers: set[asyncio.Queue[MemoryEvent]] = field(default_factory=set, init=False)
    _counter: count = field(default_factory=lambda: count(1), init=False)
    _loop: asyncio.AbstractEventLoop | None = field(default=None, init=False)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> MemoryEvent:
        event = MemoryEvent(
            event_id=f"evtbus_{next(self._counter)}",
            event_type=event_type,
            payload=payload or {},
            created_at=datetime.now(UTC).isoformat(),
            origin_id=self.origin_id,
        )
        self.deliver(event)
        if self.publisher is not None:
            self.publisher.publish(event)
        return event

    def deliver(self, event: MemoryEvent) -> None:
        self._events.append(event)
        while len(self._events) > self.history_size:
            self._events.popleft()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._deliver, event)
        else:
            self._deliver(event)

    def _deliver(self, event: MemoryEvent) -> None:
        for subscriber in list(self._subscribers):
            subscriber.put_nowait(event)

    def recent(self, limit: int = 50) -> list[MemoryEvent]:
        return list(self._events)[-limit:]

    async def subscribe(self, *, replay: int = 0) -> AsyncIterator[MemoryEvent]:
        queue: asyncio.Queue[MemoryEvent] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            for event in self.recent(replay):
                yield event
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)
