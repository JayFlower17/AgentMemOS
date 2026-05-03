from __future__ import annotations

import asyncio
import json
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

    def to_sse(self) -> str:
        data = json.dumps(
            {
                "event_id": self.event_id,
                "event_type": self.event_type,
                "payload": self.payload,
                "created_at": self.created_at,
            },
            ensure_ascii=False,
        )
        return f"id: {self.event_id}\nevent: {self.event_type}\ndata: {data}\n\n"


@dataclass
class MemoryEventBus:
    history_size: int = 100
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
        )
        self._events.append(event)
        while len(self._events) > self.history_size:
            self._events.popleft()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._deliver, event)
        else:
            self._deliver(event)
        return event

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
