import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from agentmemos.database import SessionLocal
from agentmemos.enums import AgentRole, EventType
from agentmemos.main import app
from agentmemos.models import AgentEventModel, new_id
from agentmemos.queue import InMemoryJobQueue, JobType, MemoryJob
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
