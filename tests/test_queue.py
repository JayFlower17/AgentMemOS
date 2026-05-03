import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from agentmemos.database import SessionLocal
from agentmemos.enums import AgentRole, EventType
from agentmemos.main import app
from agentmemos.models import AgentEventModel, new_id
from agentmemos.queue import InMemoryJobQueue, JobType, MemoryJob, RedisJobQueue, create_job_queue
from agentmemos.worker import MemoryWorker


def test_in_memory_job_queue_preserves_typed_jobs():
    async def run_queue_roundtrip():
        queue = InMemoryJobQueue()
        job = MemoryJob.extract_memory("evt_queue_test")

        await queue.enqueue(job)
        received = await queue.dequeue()
        queue.task_done()
        await queue.join()
        return received

    received = asyncio.run(run_queue_roundtrip())

    assert received.job_type == JobType.extract_memory
    assert received.payload["event_id"] == "evt_queue_test"


def test_memory_job_can_represent_embedding_indexing():
    job = MemoryJob.embed_memory("mem_queue_test")

    assert job.job_type == JobType.embed_memory
    assert job.payload["memory_id"] == "mem_queue_test"


def test_memory_job_json_roundtrip_preserves_type_and_payload():
    job = MemoryJob.governance_pass(
        actor="governance_test",
        duplicate_confidence_threshold=0.91,
        max_accepts=2,
    )

    restored = MemoryJob.from_json(job.to_json())

    assert restored == job


def test_memory_job_retry_policy_tracks_attempts():
    job = MemoryJob.extract_memory("evt_retry").with_retry_policy(max_attempts=2, backoff_seconds=0)
    retry_job = job.next_attempt()

    assert job.can_retry is True
    assert retry_job.attempts == 1
    assert retry_job.can_retry is False
    assert MemoryJob.from_json(retry_job.to_json()) == retry_job


def test_create_job_queue_defaults_to_in_memory_queue():
    queue = create_job_queue()

    assert isinstance(queue, InMemoryJobQueue)


def test_create_job_queue_can_build_redis_queue_when_client_is_available(monkeypatch):
    class FakeRedis:
        @classmethod
        def from_url(cls, url):
            instance = cls()
            instance.url = url
            return instance

        def rpush(self, queue_name, value):
            self.queue_name = queue_name
            self.value = value
            self.lengths = getattr(self, "lengths", {})
            self.lengths[queue_name] = self.lengths.get(queue_name, 0) + 1

        def blpop(self, queue_name):
            return queue_name, MemoryJob.extract_memory("evt_fake").to_json().encode()

        def hincrby(self, key, field, amount):
            self.hashes = getattr(self, "hashes", {})
            self.hashes.setdefault(key, {})
            self.hashes[key][field] = self.hashes[key].get(field, 0) + amount

        def hset(self, key, field, value):
            self.hashes = getattr(self, "hashes", {})
            self.hashes.setdefault(key, {})
            self.hashes[key][field] = value

        def hget(self, key, field):
            return getattr(self, "hashes", {}).get(key, {}).get(field)

        def hgetall(self, key):
            return getattr(self, "hashes", {}).get(key, {})

        def llen(self, queue_name):
            return getattr(self, "lengths", {}).get(queue_name, 0)

    import sys
    import types

    fake_module = types.SimpleNamespace(Redis=FakeRedis)
    monkeypatch.setitem(sys.modules, "redis", fake_module)

    queue = create_job_queue(
        backend="redis",
        redis_url="redis://example/0",
        redis_queue_name="agentmemos:test",
    )

    assert isinstance(queue, RedisJobQueue)
    assert queue.redis_url == "redis://example/0"
    assert queue.queue_name == "agentmemos:test"


def test_redis_queue_stats_and_dead_letter_use_operational_keys(monkeypatch):
    class FakeRedis:
        @classmethod
        def from_url(cls, url):
            return cls()

        def __init__(self):
            self.lists = {}
            self.hashes = {}

        def rpush(self, queue_name, value):
            self.lists.setdefault(queue_name, []).append(value)

        def blpop(self, queue_name):
            return queue_name, self.lists[queue_name].pop(0).encode()

        def hincrby(self, key, field, amount):
            self.hashes.setdefault(key, {})
            self.hashes[key][field] = self.hashes[key].get(field, 0) + amount

        def hset(self, key, field, value):
            self.hashes.setdefault(key, {})
            self.hashes[key][field] = value

        def hget(self, key, field):
            return self.hashes.get(key, {}).get(field)

        def hgetall(self, key):
            return self.hashes.get(key, {})

        def llen(self, queue_name):
            return len(self.lists.get(queue_name, []))

    import sys
    import types

    monkeypatch.setitem(sys.modules, "redis", types.SimpleNamespace(Redis=FakeRedis))

    async def run_redis_flow():
        queue = RedisJobQueue(redis_url="redis://example/0", queue_name="agentmemos:test")
        job = MemoryJob.extract_memory("evt_redis")
        await queue.enqueue(job)
        received = await queue.dequeue()
        queue.task_done()
        await queue.fail(received, error="redis boom")
        return queue.stats()

    stats = asyncio.run(run_redis_flow())

    assert stats["backend"] == "redis"
    assert stats["queue_name"] == "agentmemos:test"
    assert stats["enqueued"] == 1
    assert stats["dequeued"] == 1
    assert stats["completed"] == 1
    assert stats["failed"] == 1
    assert stats["dead_lettered"] == 1
    assert stats["last_error"] == "redis boom"


def test_in_memory_queue_stats_and_failure_dead_letter():
    async def run_queue():
        queue = InMemoryJobQueue()
        job = MemoryJob.extract_memory("evt_failed")
        await queue.enqueue(job)
        received = await queue.dequeue()
        await queue.fail(received, error="boom")
        queue.task_done()
        return queue.stats()

    stats = asyncio.run(run_queue())

    assert stats["backend"] == "memory"
    assert stats["enqueued"] == 1
    assert stats["dequeued"] == 1
    assert stats["completed"] == 1
    assert stats["failed"] == 1
    assert stats["dead_lettered"] == 1
    assert stats["last_error"] == "boom"


def test_worker_failure_handler_retries_then_dead_letters():
    async def run_failure_flow():
        queue = InMemoryJobQueue()
        worker = MemoryWorker(job_queue=queue)
        job = MemoryJob.embed_memory("missing").with_retry_policy(max_attempts=2, backoff_seconds=0)

        retried = await worker._handle_failure(job, RuntimeError("first failure"))
        retry_job = await queue.dequeue()
        queue.task_done()
        dead_lettered = await worker._handle_failure(retry_job, RuntimeError("second failure"))
        return retried, dead_lettered, queue.stats()

    retried, dead_lettered, stats = asyncio.run(run_failure_flow())

    assert retried is True
    assert dead_lettered is False
    assert stats["failed"] == 1
    assert stats["dead_lettered"] == 1
    assert stats["last_error"] == "second failure"


def test_worker_processes_extract_memory_job():
    with TestClient(app) as client:
        task_id = f"task_queue_extract_{uuid4().hex}"
        event_id = new_id("evt")
        with SessionLocal() as db:
            db.add(
                AgentEventModel(
                    event_id=event_id,
                    event_type=EventType.review_finding_created,
                    task_id=task_id,
                    agent_id="reviewer_1",
                    agent_role=AgentRole.reviewer,
                    content="The reviewer found that retries need bounded backoff before approval.",
                    event_metadata={},
                )
            )
            db.commit()

        asyncio.run(client.app.state.memory_worker._process_job(MemoryJob.extract_memory(event_id)))

        memories = client.get(f"/memories?task_id={task_id}&limit=200").json()
        extracted = [memory for memory in memories if memory["source_event_id"] == event_id]
        assert len(extracted) == 1
        assert extracted[0]["scope"] == "team-shared"


def test_extract_memory_job_enqueues_embedding_index_job():
    with TestClient(app) as client:
        task_id = f"task_queue_extract_embed_{uuid4().hex}"
        event_id = new_id("evt")
        with SessionLocal() as db:
            db.add(
                AgentEventModel(
                    event_id=event_id,
                    event_type=EventType.review_finding_created,
                    task_id=task_id,
                    agent_id="reviewer_1",
                    agent_role=AgentRole.reviewer,
                    content="The reviewer found that retries need bounded backoff before approval.",
                    event_metadata={},
                )
            )
            db.commit()

        worker = MemoryWorker(job_queue=InMemoryJobQueue())
        asyncio.run(worker._process_job(MemoryJob.extract_memory(event_id)))
        queued = asyncio.run(worker.job_queue.dequeue())
        worker.job_queue.task_done()

        assert queued.job_type == JobType.embed_memory
        assert queued.payload["memory_id"].startswith("mem_")


def test_worker_processes_embed_memory_job_into_vector_store():
    with TestClient(app) as client:
        response = client.post(
            "/memories",
            json={
                "task_id": f"task_queue_embed_{uuid4().hex}",
                "agent_id": "reviewer_1",
                "memory_type": "episodic",
                "scope": "team-shared",
                "content": "Retry policy requires bounded backoff before approval.",
            },
        )
        assert response.status_code == 201
        memory_id = response.json()["memory_id"]

        asyncio.run(client.app.state.memory_worker._process_job(MemoryJob.embed_memory(memory_id)))
        query_embedding = client.app.state.memory_worker.embedding_provider.embed("bounded retry backoff")
        scores = client.app.state.memory_worker.vector_store.search(query_embedding, candidate_ids=[memory_id])

        assert memory_id in scores
        assert scores[memory_id] > 0


def test_vector_assisted_retrieve_can_use_indexed_memory_when_enabled():
    with TestClient(app) as client:
        from agentmemos import main

        previous_enabled = main.settings.vector_retrieval_enabled
        previous_weight = main.settings.vector_retrieval_weight
        main.settings.vector_retrieval_enabled = True
        main.settings.vector_retrieval_weight = 0.1
        try:
            task_id = f"task_vector_retrieve_{uuid4().hex}"
            response = client.post(
                "/memories",
                json={
                    "task_id": task_id,
                    "agent_id": "reviewer_1",
                    "memory_type": "episodic",
                    "scope": "team-shared",
                    "content": "Retry policy requires bounded backoff before approval.",
                },
            )
            assert response.status_code == 201
            memory_id = response.json()["memory_id"]
            asyncio.run(client.app.state.memory_worker._process_job(MemoryJob.embed_memory(memory_id)))

            retrieve_response = client.post(
                "/retrieve",
                json={
                    "task_id": task_id,
                    "agent_id": "coder_1",
                    "agent_role": "coder",
                    "query": "bounded retry",
                    "allowed_scopes": ["team-shared"],
                },
            )
            assert retrieve_response.status_code == 200
            trace = client.get(f"/traces/{retrieve_response.json()['trace_id']}").json()
            scored = next(item for item in trace["scored_memories"] if item["memory_id"] == memory_id)
            assert scored["score_parts"]["embedding"] > 0
            assert "vector similarity" in trace["reason"]
        finally:
            main.settings.vector_retrieval_enabled = previous_enabled
            main.settings.vector_retrieval_weight = previous_weight


def test_event_ingestion_enqueues_extract_memory_job():
    with TestClient(app) as client:
        task_id = f"task_queue_ingest_{uuid4().hex}"
        response = client.post(
            "/events",
            json={
                "event_type": "review.finding.created",
                "task_id": task_id,
                "agent_id": "reviewer_1",
                "agent_role": "reviewer",
                "content": "The reviewer found that retries need bounded backoff before approval.",
            },
        )
        assert response.status_code == 202

        event_id = response.json()["event_id"]
        client.app.state.memory_worker._process_event(event_id)

        memories = client.get(f"/memories?task_id={task_id}&limit=200").json()
        assert any(memory["source_event_id"] == event_id for memory in memories)


def test_queue_status_endpoint_reports_worker_and_retry_config():
    with TestClient(app) as client:
        response = client.get("/queue/status")

        assert response.status_code == 200
        status = response.json()
        assert status["backend"] == "memory"
        assert status["queue_name"] == "memory"
        assert status["worker_running"] is True
        assert status["api_worker_enabled"] is True
        assert status["max_attempts"] >= 1
        assert "pending" in status


def test_worker_processes_governance_pass_job():
    with TestClient(app) as client:
        task_id = f"task_queue_governance_{uuid4().hex}"
        payload = {
            "task_id": task_id,
            "agent_id": "reviewer_1",
            "memory_type": "episodic",
            "scope": "team-shared",
            "content": "Retry policy requires bounded backoff limits before approval.",
        }
        client.post("/memories", json=payload)
        client.post(
            "/memories",
            json={
                **payload,
                "agent_id": "reviewer_2",
                "content": "Retry policy requires bounded backoff limits before approval and release.",
            },
        )

        asyncio.run(
            client.app.state.memory_worker._process_job(
                MemoryJob.governance_pass(
                    actor="queue_test_worker",
                    duplicate_confidence_threshold=0.85,
                    max_accepts=1,
                )
            )
        )

        actions = client.get("/memory-governance-actions?limit=20").json()
        matching = [
            action
            for action in actions
            if action["actor"] == "queue_test_worker" and action["action_type"] == "governance_pass"
        ]
        assert matching
        assert matching[0]["evidence"]["accepted_suggestions"] == 1
