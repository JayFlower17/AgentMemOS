from __future__ import annotations

import asyncio
import signal

from agentmemos.config import get_settings
from agentmemos.database import init_db
from agentmemos.event_bus import MemoryEventBus, RedisEventPublisher
from agentmemos.queue import create_job_queue
from agentmemos.vector import create_vector_store
from agentmemos.worker import MemoryWorker


async def run_worker() -> None:
    settings = get_settings()
    init_db()
    event_bus = None
    if settings.redis_event_fanout_enabled:
        event_bus = MemoryEventBus(
            publisher=RedisEventPublisher(redis_url=settings.redis_url, channel=settings.redis_event_channel)
        )
    worker = MemoryWorker(
        job_queue=create_job_queue(
            backend=settings.job_queue_backend,
            redis_url=settings.redis_url,
            redis_queue_name=settings.redis_queue_name,
        ),
        vector_store=create_vector_store(backend=settings.vector_store_backend),
        event_bus=event_bus,
    )
    stop_event = asyncio.Event()

    def request_stop() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: request_stop())

    await worker.start()
    try:
        await stop_event.wait()
    finally:
        await worker.stop()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
