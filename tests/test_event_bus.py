from uuid import uuid4

from fastapi.testclient import TestClient

from agentmemos.event_bus import MemoryEvent, MemoryEventBus
from agentmemos.main import app


def test_memory_event_bus_formats_sse_events():
    bus = MemoryEventBus()

    event = bus.publish("memory.created", {"memory_id": "mem_test"})

    assert bus.recent(1) == [event]
    assert "event: memory.created" in event.to_sse()
    assert '"memory_id": "mem_test"' in event.to_sse()


def test_memory_event_json_roundtrip_preserves_origin():
    event = MemoryEvent(
        event_id="evtbus_1",
        event_type="job.completed",
        payload={"job_type": "extract_memory"},
        created_at="2026-05-03T00:00:00+00:00",
        origin_id="bus_test",
    )

    restored = MemoryEvent.from_json(event.to_json())

    assert restored == event


def test_memory_event_bus_can_publish_to_external_fanout():
    class FakePublisher:
        def __init__(self):
            self.events = []

        def publish(self, event):
            self.events.append(event)

    publisher = FakePublisher()
    bus = MemoryEventBus(origin_id="bus_api", publisher=publisher)

    event = bus.publish("memory.created", {"memory_id": "mem_fanout"})

    assert publisher.events == [event]
    assert event.origin_id == "bus_api"


def test_memory_event_bus_can_deliver_remote_events_without_republishing():
    class FakePublisher:
        def __init__(self):
            self.events = []

        def publish(self, event):
            self.events.append(event)

    publisher = FakePublisher()
    bus = MemoryEventBus(origin_id="bus_api", publisher=publisher)
    remote = MemoryEvent(
        event_id="evtbus_remote",
        event_type="memory.extracted",
        payload={"memory_id": "mem_remote"},
        created_at="2026-05-03T00:00:00+00:00",
        origin_id="bus_worker",
    )

    bus.deliver(remote)

    assert bus.recent(1) == [remote]
    assert publisher.events == []


def test_event_stream_route_is_registered():
    route_paths = {route.path for route in app.routes}

    assert "/events/stream" in route_paths


def test_memory_create_publishes_realtime_events():
    with TestClient(app) as client:
        task_id = f"task_sse_{uuid4().hex}"

        response = client.post(
            "/memories",
            json={
                "task_id": task_id,
                "agent_id": "coder_1",
                "memory_type": "episodic",
                "scope": "task-local",
                "content": "SSE should publish manual memory writes.",
            },
        )

        assert response.status_code == 201
        memory_id = response.json()["memory_id"]
        recent = client.app.state.event_bus.recent(20)
        event_types = {event.event_type for event in recent}

        assert "memory.created" in event_types
        assert "job.enqueued" in event_types
        created = next(event for event in recent if event.event_type == "memory.created")
        assert created.payload["memory_id"] == memory_id
