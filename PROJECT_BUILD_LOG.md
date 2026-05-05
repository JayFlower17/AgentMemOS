# AgentMemOS Project Build Log

This document records implementation progress, design decisions, verification, and next-step direction for the AgentMemOS MVP.

Current branch: `JayFlower`

## Current Stage

AgentMemOS has completed the first MVP loop and is now in the memory governance and self-maintenance phase.

Completed core loop:

1. Event ingestion through `POST /events`.
2. Worker-based memory extraction.
3. Scoped memory persistence with `agent-local`, `task-local`, `team-shared`, and `project-global`.
4. Role-aware retrieval through `POST /retrieve`.
5. Retrieval trace recording and explainability.
6. Memory write decision traces.
7. Memory status governance with `active`, `superseded`, and `archived`.
8. Memory relation governance with `supersedes`, `conflicts_with`, and `duplicates`.
9. Governance-aware retrieval.
10. Agent-readable governance insights and relation suggestions.

The dashboard remains a development aid for inspecting the system, not the primary product surface.

## Build History

### `46b5979` Initial AgentMemOS MVP

- Built the initial FastAPI MVP.
- Added event ingestion, memory persistence, and scoped retrieval.
- Established the SQLite local development path.

Verification:

- Initial test suite passed.

### `0d5059c` Add memory status audit history

- Added memory status transitions.
- Added auditable status decision history.
- Introduced active/archive/supersede lifecycle semantics.

### `165406a` Explain retrieval trace scoring

- Added score parts for retrieval candidates.
- Made retrieval scoring explainable by importance, confidence, scope, role/type affinity, and keyword overlap.

### `eff895b` Add dashboard trace explain view

- Added a trace explain panel to inspect retrieval behavior.
- Exposed selected, scored, and filtered memories.

### `5b4858d` Improve trace explain dashboard guidance

- Improved dashboard guidance for reading trace explain output.
- Clarified selected and filtered memory panels.

### `523ba89` Add memory write decision traces

- Added write decision traces for memory creation.
- Recorded why a memory was extracted or manually created, including type, scope, confidence, importance, reason, and signals.

### `222c911` Show memory write decisions on dashboard

- Exposed memory write decisions in the dashboard.
- Made write path and classification visible during development.

### `cafc5aa` Add demo data seeding script

- Added `examples/seed_demo_data.py`.
- Seed script creates demo events, memories, and retrieval traces.

### `a4b8a41` Prefer extracted memory decisions in dashboard

- Adjusted dashboard selection to prefer more informative extracted decisions.

### `9f5dbfc` Inline memory decisions in memory cards

- Moved memory write decision details into memory cards.
- Reduced the need for a separate decision-only panel.

### `229934a` Document memory write paths in dashboard guide

- Added guide text explaining `manual`, `extracted`, and memory type distinctions.

### `350e625` Deduplicate repeated memory writes

- Added exact normalized duplicate detection.
- Reused existing active memory for repeated writes.
- Added `deduplicated` memory decision trace instead of silently dropping duplicate writes.

Verification:

- `pytest -q`: passed.
- `node --check agentmemos/static/app.js`: passed.

### `54c8b24` Add memory governance relations

- Added memory relation model and APIs.
- Supported `supersedes`, `conflicts_with`, and `duplicates`.
- `supersedes` automatically marks the target memory as `superseded`.
- Added relation display to memory cards for development inspection.

Verification:

- `pytest -q`: 13 passed.

### `540de6b` Clarify memory relation guide copy

- Expanded the help card explanation for memory relations.
- Clarified source/target direction and the effect of `supersedes`.

### `149cae3` Apply memory governance during retrieval

- Retrieval now applies memory governance.
- `archived` and `superseded` memories are filtered out of selected results.
- Retrieval trace records governance filter reasons.
- Trace scored candidates can include open relation warnings.

Verification:

- `pytest -q`: 13 passed.
- `node --check agentmemos/static/app.js`: passed.
- Confirmed `/traces?limit=1` showed governance-aware filtering.

### `2dfe92b` Add memory governance insights API

- Added `GET /memory-insights`.
- Aggregates open memory relations and retrieval traces into agent-readable action items.
- Added insight types:
  - `open_conflicts_with`
  - `retrieval_miss`
  - `low_confidence_selection`
  - `governance_warning_selected`
  - `open_duplicates`
  - `open_supersedes`

Verification:

- `pytest -q`: 14 passed.
- Confirmed `/memory-insights?limit=3` returned structured governance action items.

### `cdd7e18` Suggest memory governance relations

- Added `GET /memory-relation-suggestions`.
- Suggests possible `duplicates` and `conflicts_with` relations between active memories.
- Suggestions are read-only and do not mutate memory state.
- Each suggestion includes confidence, evidence, reason, and suggested action.

Verification:

- `pytest -q`: 15 passed.
- Confirmed `/memory-relation-suggestions?limit=3` returned duplicate candidates.

### Accept memory governance suggestions

- Added an acceptance path for still-valid memory relation suggestions.
- Accepting a suggestion creates the corresponding memory relation.
- Acceptance writes an auditable governance action.
- Added `GET /memory-governance-actions` for action history.

Verification:

- `pytest -q`: 16 passed.

### Add governance agent example

- Added `examples/governance_agent.py`.
- The example fetches `/memory-insights` and `/memory-relation-suggestions`.
- It accepts only high-confidence duplicate suggestions.
- The default run is capped by `AGENTMEMOS_GOVERNANCE_MAX_ACCEPTS`.
- It prints unresolved conflicts for explicit review instead of resolving them automatically.

Verification:

- `python -m py_compile examples/governance_agent.py`: passed.
- `pytest -q`: 16 passed.
- Confirmed the script connected to local 8014 and accepted duplicate suggestions.

### Add governance run endpoint

- Added `POST /governance/run`.
- The endpoint runs a conservative server-side governance pass.
- It accepts high-confidence duplicate suggestions up to a configurable limit.
- It skips conflicts and records conflict counts for explicit review.
- It writes a `governance_pass` summary action.

Verification:

- `python -m py_compile agentmemos/main.py agentmemos/schemas.py`: passed.
- `pytest -q`: 17 passed.

### Refactor governance logic into service module

- Added `agentmemos/governance.py`.
- Moved memory insights, relation suggestions, suggestion acceptance, and governance pass logic out of `main.py`.
- Kept `main.py` focused on API routing and response assembly.
- Preserved endpoint behavior while making governance logic easier to test and evolve.

Verification:

- `python -m py_compile agentmemos/main.py agentmemos/governance.py`: passed.
- `pytest -q`: 19 passed.

### Harden SQLite schema compatibility

- Replaced one-off retrieval trace column patching with a general SQLite schema ensure path.
- Added known-column compatibility checks for retrieval traces, memory relations, and governance actions.
- Added a database schema regression test for adding a missing known column.

Verification:

- `python -m py_compile agentmemos/database.py`: passed.
- `pytest -q tests/test_database_schema.py`: 1 passed.
- `pytest -q`: 20 passed.

### Upgrade structured memory extraction

- Reworked the extractor from direct event-type mapping into a structured rule decision path.
- Added content signal detection for risk, failure, decision, procedure, and scratch/local-note language.
- Extraction decisions now record the extractor version and applied rules in memory write decision signals.
- Task completion can now become procedural team knowledge only when the content reads like reusable guidance.
- Coder tool observations stay agent-local when explicitly marked as scratch, while normal tool evidence becomes task-local.
- Added extractor unit tests, including Chinese signal detection coverage.

Verification:

- `python -m py_compile agentmemos/extractor.py`: passed.
- `pytest -q`: 24 passed.

### Add governance background scheduler

- Added `agentmemos/jobs.py` with a lightweight `GovernanceScheduler`.
- Wired the scheduler into FastAPI lifespan alongside the memory extraction worker.
- Scheduler is disabled by default and can be enabled by environment variables.
- Added scheduler configuration:
  - `AGENTMEMOS_GOVERNANCE_SCHEDULER_ENABLED`
  - `AGENTMEMOS_GOVERNANCE_SCHEDULER_INTERVAL_SECONDS`
  - `AGENTMEMOS_GOVERNANCE_SCHEDULER_ACTOR`
  - `AGENTMEMOS_GOVERNANCE_DUPLICATE_CONFIDENCE_THRESHOLD`
  - `AGENTMEMOS_GOVERNANCE_MAX_ACCEPTS`
- Added `GET /governance/scheduler` to inspect scheduler state, thresholds, last run summary, and last error.
- Added tests for one-shot scheduler execution and default disabled status.

Verification:

- `python -m py_compile agentmemos/jobs.py agentmemos/main.py agentmemos/config.py agentmemos/schemas.py`: passed.
- `pytest -q`: 26 passed.

### Add JobQueue boundary

- Added `agentmemos/queue.py`.
- Introduced typed jobs:
  - `extract_memory`
  - `governance_pass`
- Added `MemoryJob`, `JobType`, `JobQueue`, and `InMemoryJobQueue`.
- Refactored `MemoryWorker` to consume typed jobs instead of raw event IDs.
- Kept `MemoryWorker.enqueue(event_id)` for backward-compatible event ingestion.
- Governance scheduler can now enqueue governance pass jobs when connected to a queue.
- FastAPI lifespan now wires the scheduler to the worker's queue.
- Added queue and worker job tests.
- Adjusted memory flow test to tolerate asynchronous duplicate audit ordering.

Verification:

- `python -m py_compile agentmemos/queue.py agentmemos/worker.py agentmemos/jobs.py agentmemos/main.py`: passed.
- `pytest -q`: 30 passed.

### Add repository boundary

- Added `agentmemos/repositories.py`.
- Introduced thin SQLAlchemy-backed repositories:
  - `EventRepository`
  - `MemoryRepository`
  - `TraceRepository`
  - `GovernanceRepository`
- Moved core API persistence access for events, memory listing/details, memory decisions, promotions, status history, traces, relations, and governance actions behind repository methods.
- Kept repositories returning SQLAlchemy models for now to preserve existing serializers and endpoint behavior.
- Added repository tests for event creation/listing, memory lifecycle history, and relation lookup/resolution.

Verification:

- `python -m py_compile agentmemos/repositories.py agentmemos/main.py`: passed.
- `pytest -q`: 33 passed.

### Add service orchestration layer

- Added `agentmemos/services.py`.
- Introduced service-layer orchestration:
  - `EventIngestionService`
  - `MemoryLifecycleService`
  - `GovernanceRelationService`
- Event ingestion now creates the event through `EventRepository` and enqueues an `extract_memory` job through `JobQueue`.
- Memory promotion and status updates now flow through `MemoryLifecycleService`.
- Relation resolution now flows through `GovernanceRelationService`.
- API routes remain behavior-compatible but now act more like HTTP adapters.
- Added service tests for event ingestion/job enqueue, memory lifecycle, and relation resolution.

Verification:

- `python -m py_compile agentmemos/services.py agentmemos/main.py`: passed.
- `pytest -q`: 36 passed.

### Add embedding/vector retrieval boundary

- Added `agentmemos/vector.py`.
- Introduced vector interfaces and local implementations:
  - `EmbeddingProvider`
  - `VectorStore`
  - `HashingEmbeddingProvider`
  - `InMemoryVectorStore`
- Added vector utility functions for tokenization, cosine similarity, and memory embedding text.
- Retrieval scoring now accepts optional embedding scores.
- Embedding score weight is currently `0.0`, so existing lexical retrieval behavior remains unchanged.
- Added vector tests and retrieval scoring boundary coverage.

Verification:

- `python -m py_compile agentmemos/vector.py agentmemos/retrieval.py`: passed.
- `pytest -q`: 40 passed.

### Add embedding indexing job

- Added `embed_memory` as a typed `JobType`.
- Added `MemoryJob.embed_memory(memory_id)`.
- `MemoryWorker` now owns an `EmbeddingProvider` and `VectorStore`.
- `MemoryWorker` can process `embed_memory` jobs and index memory text into `InMemoryVectorStore`.
- `extract_memory` jobs now enqueue `embed_memory` after a memory record is created.
- Manual memory creation through `POST /memories` now also enqueues `embed_memory`.
- Added queue/worker tests for embedding job representation, extraction-to-indexing handoff, and vector store indexing.

Verification:

- `python -m py_compile agentmemos/queue.py agentmemos/worker.py agentmemos/main.py`: passed.
- `pytest -q`: 43 passed.

### Add optional vector-assisted retrieval

- Added vector retrieval configuration:
  - `AGENTMEMOS_VECTOR_RETRIEVAL_ENABLED`
  - `AGENTMEMOS_VECTOR_RETRIEVAL_WEIGHT`
- Retrieval scoring now accepts a configurable embedding weight.
- `POST /retrieve` can use the worker's local vector store when vector retrieval is enabled.
- Retrieval trace `score_parts` includes `embedding` only when an embedding score is applied.
- Default behavior remains lexical because vector retrieval is disabled and weight defaults to `0.0`.
- Added tests for default scoring, weighted embedding scoring, and API-level vector-assisted retrieval.

Verification:

- `python -m py_compile agentmemos/config.py agentmemos/retrieval.py agentmemos/main.py`: passed.
- `pytest -q`: 45 passed.

### Add optional Redis job queue

- Added `RedisJobQueue` behind the existing `JobQueue` interface.
- Added JSON serialization/deserialization for typed `MemoryJob` payloads.
- Added `create_job_queue(...)` factory.
- Added optional dependency group `redis`.
- Added queue backend configuration:
  - `AGENTMEMOS_JOB_QUEUE_BACKEND`
  - `AGENTMEMOS_REDIS_URL`
  - `AGENTMEMOS_REDIS_QUEUE_NAME`
- FastAPI lifespan now constructs the configured queue and passes it to `MemoryWorker`.
- Default backend remains `memory`, so local development and tests still use `InMemoryJobQueue`.
- Added tests for job JSON roundtrip, queue factory defaults, and Redis queue construction with a fake Redis client.

Verification:

- `python -m py_compile agentmemos/queue.py agentmemos/config.py agentmemos/main.py`: passed.
- `pytest -q`: 48 passed.

### Add durable SQLite vector store

- Added `MemoryEmbeddingModel` and `memory_embeddings` table.
- Added vector store configuration:
  - `AGENTMEMOS_VECTOR_STORE_BACKEND`
- Added `SqliteVectorStore`.
- Added `create_vector_store(...)` factory.
- FastAPI lifespan now creates the configured vector store and passes it to `MemoryWorker`.
- Default vector store remains `memory`; `sqlite` can be enabled for durable local vector indexes.
- Added tests for SQLite vector persistence across store instances, vector store factory behavior, and memory embedding table creation.

Verification:

- `python -m py_compile agentmemos/models.py agentmemos/vector.py agentmemos/config.py agentmemos/main.py`: passed.
- `pytest -q`: 51 passed.

### Expand Python SDK client

- Expanded `AgentMemOSClient` as the common SDK layer for future adapters.
- Added SDK methods for:
  - event listing
  - trace listing and detail reads
  - memory relation creation/listing/resolution
  - memory insights
  - relation suggestions and suggestion acceptance
  - governance pass execution
  - governance scheduler status
  - governance action listing
- Kept SDK dependency-free by using the Python standard library HTTP stack.
- Preserved injectable transport for tests and adapter integration.
- Updated SDK usage example to default to local port `8014` and demonstrate insights/governance calls.

Verification:

- `python -m py_compile agentmemos/sdk.py examples/sdk_usage.py`: passed.
- `pytest -q`: 54 passed.

### Add LangGraph-style adapter

- Added `LangGraphMemoryAdapter` without requiring `langgraph` as a dependency.
- Added graph/node-style hooks:
  - `before_node(state)`
  - `after_node(before, after)`
  - `wrap_node(node)`
- Adapter retrieves memory before node execution and emits an AgentMemOS event after node execution.
- Preserved existing `MemoryStepAdapter`.
- Updated adapter example to default to local port `8014` and show both step and graph-style wrapping.
- Added adapter tests for before/after hooks and node wrapping.

Verification:

- `python -m py_compile agentmemos/adapters.py examples/adapter_usage.py`: passed.
- `pytest -q`: 56 passed.

### Add MCP tool integration layer

- Added MCP-ready tool definitions for core AgentMemOS operations:
  - emit event
  - retrieve memories
  - create memory
  - list memories
  - list governance insights
  - run governance pass
- Added `AgentMemOSMCPToolbox` as a runtime-neutral dispatcher backed by the Python SDK.
- Added `AgentMemOSMCPServer`, a small JSON-RPC binding for initialize, ping, tools/list, and tools/call.
- Kept the integration free of a hard MCP SDK dependency so the current local service remains lightweight.
- Added `build_default_toolbox()` with the project dev server default `http://127.0.0.1:8014`.
- Added example scripts showing direct toolbox usage and a stdio-style JSON-RPC server entrypoint.
- Added unit tests for schema listing, SDK dispatch, argument coercion, server request handling, and error handling.

Verification:

- `python -m py_compile agentmemos/mcp_tools.py agentmemos/mcp_server.py examples/mcp_tool_usage.py examples/mcp_stdio_server.py agentmemos/__init__.py`: passed.
- `pytest -q`: 63 passed.

### Bind MCP tools to official SDK runtime

- Added optional dependency extra `agentmemos[mcp]` backed by the official `mcp[cli]` Python SDK.
- Added `agentmemos.mcp_runtime` with a FastMCP server factory and runtime entrypoint.
- Registered AgentMemOS tools with official FastMCP decorators:
  - `agentmemos_emit_event`
  - `agentmemos_retrieve`
  - `agentmemos_create_memory`
  - `agentmemos_list_memories`
  - `agentmemos_list_insights`
  - `agentmemos_run_governance`
- Preserved the no-extra-dependency lightweight JSON-RPC binding for local testing and fallback.
- Added `examples/mcp_fastmcp_server.py` for stdio or streamable-http transport.
- Added package console scripts:
  - `agentmemos-mcp`
  - `agentmemos-mcp-jsonrpc`
- Documented MCP startup paths in the README.
- Added tests that verify the FastMCP registration layer without requiring the optional SDK during normal test runs.

Verification:

- `python -m py_compile agentmemos/mcp_runtime.py agentmemos/mcp_server.py examples/mcp_fastmcp_server.py agentmemos/__init__.py`: passed.
- `pytest -q`: 64 passed.

### Add MCP client configuration and smoke test

- Added explicit MCP tool to AgentMemOS API route mapping in code.
- Added `describe_mcp_tool_routes()` for docs, agent prompts, and future runtime metadata.
- Added MCP client configuration examples for:
  - installed package command
  - source checkout on Windows
  - lightweight JSON-RPC fallback
- Added `examples/mcp_smoke_test.py` to run `tools/list` and `tools/call` against the local AgentMemOS service.
- Updated README with smoke test usage and tool-to-API mapping.
- Added tests ensuring every registered MCP tool has a route mapping.

Verification:

- `python -m py_compile agentmemos/mcp_tools.py examples/mcp_smoke_test.py agentmemos/__init__.py`: passed.
- `pytest -q`: 65 passed.
- `python examples/mcp_smoke_test.py`: passed against `http://127.0.0.1:8014`.

### Add SSE realtime event stream

- Added `MemoryEventBus` for process-local realtime event publishing.
- Added `GET /events/stream` as an SSE endpoint with recent event replay.
- Published realtime events for:
  - agent event ingestion
  - job enqueue/start/complete/failure
  - manual memory creation
  - extracted memory creation
  - embedding indexing completion
  - memory promotion
  - memory status updates
  - memory relation creation/resolution
  - governance pass completion
  - governance suggestion acceptance
- Wired `MemoryWorker` to emit job, extraction, embedding, and governance events.
- Added `examples/sse_watch.py` to subscribe to the event stream from a running service.
- Updated README with SSE usage and event names.
- Added tests for SSE event formatting, route registration, and memory write event publishing.

Verification:

- `python -m py_compile agentmemos/event_bus.py agentmemos/main.py agentmemos/worker.py agentmemos/services.py examples/sse_watch.py`: passed.
- `pytest -q`: 68 passed.

### Operationalize Redis queues and independent workers

- Extended `MemoryJob` with retry metadata:
  - `attempts`
  - `max_attempts`
  - `backoff_seconds`
- Added queue stats to the `JobQueue` boundary.
- Added in-memory queue counters for:
  - pending
  - enqueued
  - dequeued
  - completed
  - failed
  - dead-lettered
  - last error
- Extended `RedisJobQueue` with:
  - stats hash
  - dead-letter queue
  - queue length reporting
  - failure recording
- Added worker retry/backoff handling with `job.retried` and `job.dead_lettered` realtime events.
- Added configurable retry settings:
  - `AGENTMEMOS_JOB_MAX_ATTEMPTS`
  - `AGENTMEMOS_JOB_RETRY_BACKOFF_SECONDS`
- Added `AGENTMEMOS_API_WORKER_ENABLED` to allow API-only mode when running independent workers.
- Added `agentmemos.worker_app` and package script `agentmemos-worker`.
- Added `GET /queue/status` for queue depth, worker state, retry config, and dead-letter counters.
- Updated README with Redis queue, independent worker, retry, and queue status instructions.
- Added tests for retry serialization, in-memory stats, Redis stats/dead-letter behavior, worker failure handling, and queue status endpoint.

Verification:

- `python -m py_compile agentmemos/queue.py agentmemos/worker.py agentmemos/worker_app.py agentmemos/main.py agentmemos/services.py agentmemos/config.py agentmemos/schemas.py`: passed.
- `pytest -q`: 73 passed.

### Add Redis local validation compose and smoke test

- Added `docker-compose.redis.yml` for one-command local Redis startup.
- Redis compose uses `redis:7-alpine`, exposes `6379`, persists data to a named Docker volume, and includes a healthcheck.
- Added `examples/redis_queue_smoke_test.py` to verify:
  - API can connect to a Redis-backed queue.
  - Event ingestion enqueues extraction work.
  - An external worker consumes the job and creates memory.
  - `/queue/status` remains available before and after the flow.
- Updated README with:
  - Docker Compose Redis startup.
  - API-only mode.
  - independent worker startup.
  - Redis queue smoke test.
  - Redis shutdown command.

Verification:

- `python -m py_compile examples/redis_queue_smoke_test.py`: passed.
- `pytest -q`: 73 passed.
- `docker compose -f docker-compose.redis.yml config`: passed.

### Run real Redis queue E2E smoke test

- Started a real Redis container from `docker-compose.redis.yml`.
- Installed the optional Python Redis client in the local environment for the smoke test.
- Added `examples/redis_queue_e2e_smoke.py` after manual shell startup exposed fragile environment quoting on Windows.
- The E2E smoke runner:
  - flushes Redis DB 0
  - starts AgentMemOS API in Redis/API-only mode
  - starts an independent `agentmemos.worker_app` process
  - verifies `/queue/status` reports Redis backend and API worker disabled
  - emits an event through the SDK
  - waits until the independent worker extracts a memory
  - prints queue status before and after
  - terminates child processes cleanly
- Updated README with the one-command E2E smoke runner.

Verification:

- `docker compose -f docker-compose.redis.yml up -d`: passed; Redis container became healthy.
- `docker exec agentmemos-redis redis-cli ping`: passed with `PONG`.
- `pip install "redis>=5"`: installed Redis Python client for the local smoke test environment.
- `python -m py_compile examples/redis_queue_e2e_smoke.py examples/redis_queue_smoke_test.py`: passed.
- First direct script run exposed missing repo-root import path; fixed `examples/redis_queue_e2e_smoke.py`.
- `python examples/redis_queue_e2e_smoke.py`: passed.
  - `/queue/status` before: Redis backend, API worker disabled, empty queue.
  - `/queue/status` after: `enqueued=2`, `dequeued=2`, `completed=2`, `failed=0`, `dead_lettered=0`.
  - Extracted memory from independent worker: `mem_955ec718ffd34737`.
- `pytest -q`: 76 passed.

### Add Redis pub/sub backed SSE fanout

- Added Redis-backed event fanout configuration:
  - `AGENTMEMOS_REDIS_EVENT_FANOUT_ENABLED`
  - `AGENTMEMOS_REDIS_EVENT_CHANNEL`
- Extended `MemoryEvent` with JSON serialization and `origin_id`.
- Added `RedisEventPublisher` and `RedisEventSubscriber`.
- Updated `MemoryEventBus` to:
  - publish local events to Redis when fanout is enabled
  - deliver remote Redis events into local SSE subscribers
  - avoid echoing same-origin events back into the API process
- Updated FastAPI lifespan to start a Redis pub/sub listener when fanout is enabled.
- Updated independent worker startup to publish worker events to Redis.
- Extended Redis E2E smoke runner to enable fanout and verify worker `memory.extracted` appears in `/events/stream` replay.
- Updated README with Redis SSE fanout configuration.
- Added tests for event JSON roundtrip, publisher handoff, and remote event delivery without republishing.

Verification:

- `python -m py_compile agentmemos/event_bus.py agentmemos/main.py agentmemos/worker_app.py examples/redis_queue_e2e_smoke.py`: passed.
- `pytest -q tests/test_event_bus.py`: 6 passed.
- First fanout E2E run exposed local proxy interference when reading SSE through `urllib`; fixed by disabling proxies with `ProxyHandler({})`.
- Second fanout E2E run exposed SSE long-read behavior; fixed by reading SSE lines until the target event or timeout.
- `python examples/redis_queue_e2e_smoke.py`: passed against real Redis.
  - `/queue/status` before: Redis backend, API worker disabled, empty queue.
  - `/queue/status` after: `enqueued=2`, `dequeued=2`, `completed=2`, `failed=0`, `dead_lettered=0`.
  - Independent worker extracted memory: `mem_65de217f0bfe48f4`.
  - Redis SSE fanout verified: `memory.extracted` observed through API `/events/stream` replay.
- `pytest -q`: 79 passed.

### Add pgvector storage adapter and local validation path

- Added optional `postgres` dependency extra with `psycopg[binary]`.
- Added pgvector configuration:
  - `AGENTMEMOS_VECTOR_STORE_BACKEND=pgvector`
  - `AGENTMEMOS_PGVECTOR_URL`
  - `AGENTMEMOS_PGVECTOR_TABLE_NAME`
  - `AGENTMEMOS_PGVECTOR_DIMENSIONS`
- Added `PgVectorStore` with:
  - `CREATE EXTENSION IF NOT EXISTS vector`
  - vector table creation
  - HNSW cosine index creation
  - upsert by `memory_id`
  - cosine distance search with optional candidate filtering
- Preserved existing memory and SQLite vector stores as defaults.
- Added `docker-compose.pgvector.yml` for one-command local pgvector startup.
- Added `examples/pgvector_smoke_test.py` to validate memory creation, indexing, and retrieval through the running API.
- Updated README with pgvector startup, configuration, smoke test, and shutdown commands.
- Added tests for pgvector setup SQL, upsert SQL, search SQL, candidate filtering, and dimension validation.

Verification:

- `python -m py_compile agentmemos/vector.py agentmemos/config.py examples/pgvector_smoke_test.py`: passed.
- `pytest -q tests/test_vector.py`: 8 passed.
- `docker compose -f docker-compose.pgvector.yml config`: passed.
- `pytest -q`: 76 passed.

### Run real pgvector E2E smoke test

- Started a real pgvector container from `docker-compose.pgvector.yml`.
- Installed the optional local `psycopg[binary]` dependency for the smoke test environment.
- Added `examples/pgvector_e2e_smoke.py` to avoid fragile shell environment quoting on Windows.
- The E2E smoke runner:
  - starts AgentMemOS API with `AGENTMEMOS_VECTOR_STORE_BACKEND=pgvector`
  - enables vector-assisted retrieval
  - creates a memory through the API
  - waits for the API-owned worker to index the embedding into pgvector
  - retrieves using a related query
  - verifies the retrieval trace includes positive embedding score contribution
  - terminates the child API process cleanly
- Updated README with the pgvector E2E runner.

Verification:

- `docker compose -f docker-compose.pgvector.yml up -d`: passed; pgvector container became healthy.
- `docker exec agentmemos-pgvector pg_isready -U agentmemos -d agentmemos`: passed.
- `pip install "psycopg[binary]>=3"`: installed pgvector client dependency for the local smoke environment.
- `python -m py_compile examples/pgvector_e2e_smoke.py examples/pgvector_smoke_test.py`: passed.
- `python examples/pgvector_e2e_smoke.py`: passed.
  - Created memory: `mem_024265d2744645cb`.
  - Retrieval trace: `trace_ac7de5375feb49b3`.
  - Embedding score contribution: `0.0603`.
- `pytest -q`: 79 passed.

### Add GitHub Actions CI

- Added `.github/workflows/ci.yml`.
- CI runs on:
  - pushes to `JayFlower`
  - pushes to `main`
  - pushes to `master`
  - pull requests
- CI matrix covers Python 3.11 and 3.12.
- CI steps:
  - checkout
  - setup Python with pip cache
  - install `.[dev]`
  - compile `agentmemos` and `examples`
  - run `pytest -q`
- Updated README with CI coverage summary.

Verification:

- `python -m compileall -q agentmemos examples`: passed.
- `pytest -q`: 79 passed.

### Refactor extractor into provider boundary

- Added structured `ExtractionResult` with:
  - `should_write`
  - `memory`
  - `reason`
  - `signals`
  - `provider`
- Added `ExtractorProvider` protocol.
- Wrapped the existing rule-based logic in `RuleBasedExtractor`.
- Added `create_extractor_provider()` factory.
- Added `AGENTMEMOS_EXTRACTOR_BACKEND`, defaulting to `rule`.
- Preserved legacy compatibility functions:
  - `extract_memory(event)`
  - `explain_extraction(event, memory)`
- Updated `MemoryWorker` to accept an injected extractor provider.
- Kept current rule-based behavior and decision traces stable.
- Updated README with extractor provider explanation.
- Added tests for:
  - structured rule-based extraction results
  - empty-content skip decisions
  - provider factory
  - worker extractor injection

Verification:

- `python -m py_compile agentmemos/extractor.py agentmemos/worker.py agentmemos/config.py`: passed.
- `pytest -q tests/test_extractor.py tests/test_queue.py`: 24 passed.
- `python -m compileall -q agentmemos examples`: passed.
- `pytest -q`: 83 passed.

### Add OpenAI-compatible LLM extractor provider

- Added `OpenAIChatExtractor`.
- Supports OpenAI-compatible chat completions APIs through:
  - `AGENTMEMOS_OPENAI_API_KEY`
  - `OPENAI_API_KEY`
  - `AGENTMEMOS_OPENAI_BASE_URL`
  - `AGENTMEMOS_OPENAI_EXTRACTOR_MODEL`
  - `AGENTMEMOS_OPENAI_EXTRACTOR_TIMEOUT_SECONDS`
- Extended `AGENTMEMOS_EXTRACTOR_BACKEND` to support `openai`.
- LLM extractor asks for strict JSON with:
  - `should_write`
  - `memory_type`
  - `scope`
  - `content`
  - `summary`
  - `confidence`
  - `importance`
  - `reason`
  - `signals`
- Added fallback behavior:
  - missing API key falls back to rule extractor
  - failed LLM call falls back to rule extractor
  - fallback reason is recorded in extraction signals
- Added `examples/openai_extractor_smoke.py` for local OpenAI-compatible/DeepSeek testing without committing any key.
- Updated README with OpenAI-compatible and DeepSeek configuration examples.
- Added unit tests for:
  - successful structured LLM extraction
  - LLM declining memory writes
  - fallback to rule extractor on LLM failure

Verification:

- `python -m py_compile agentmemos/extractor.py agentmemos/config.py examples/openai_extractor_smoke.py`: passed.
- `pytest -q tests/test_extractor.py`: 12 passed.
- First real DeepSeek smoke exposed multi-provider key-file parsing and error redaction needs; fixed with labeled key-file parsing and secret redaction.
- Second real DeepSeek smoke exposed fragile shell env propagation; fixed `examples/openai_extractor_smoke.py` to infer DeepSeek defaults from the local labeled key file when no explicit env is set.
- `python examples/openai_extractor_smoke.py`: passed against DeepSeek using local key file.
  - Provider: `openai`.
  - Model: `deepseek-chat`.
  - Fallback: `False`.
  - Result: wrote procedural task-local memory.
- `python -m compileall -q agentmemos examples`: passed.
- `pytest -q`: 88 passed.

### Add OpenAI-compatible embedding provider

- Added configurable embedding provider selection:
  - `AGENTMEMOS_EMBEDDING_PROVIDER=hashing|openai`
  - `AGENTMEMOS_OPENAI_EMBEDDING_API_KEY`
  - `AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_FILE`
  - `AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_LABEL`
  - `AGENTMEMOS_OPENAI_EMBEDDING_BASE_URL`
  - `AGENTMEMOS_OPENAI_EMBEDDING_MODEL`
  - `AGENTMEMOS_OPENAI_EMBEDDING_DIMENSIONS`
  - `AGENTMEMOS_OPENAI_EMBEDDING_TIMEOUT_SECONDS`
- Added `OpenAIEmbeddingProvider` for OpenAI-compatible `/embeddings` APIs.
- Kept local hashing embeddings as the default zero-config provider.
- Updated vector store metadata so SQLite and pgvector record the active embedding provider.
- Added `examples/openai_embedding_smoke.py` for local third-party embedding validation without committing secrets.
- Documented key-file labels and pgvector dimension compatibility.

Verification:

- `python -m py_compile agentmemos/vector.py agentmemos/config.py agentmemos/worker.py examples/openai_embedding_smoke.py`: passed.
- `pytest -q tests/test_vector.py`: 11 passed.
- `pytest -q`: 91 passed.
- First local smoke exposed missing repo-root import path in `examples/openai_embedding_smoke.py`; fixed.
- `python examples/openai_embedding_smoke.py`: passed against the local third-party OpenAI-compatible embedding provider using the desktop labeled key file.
  - Base URL: `https://api.jiekou.ai/openai`.
  - Model: `text-embedding-3-large`.
  - Returned dimensions: `3072`.

### Add Chinese project overview document

- Added `docs/AgentMemOS_中文项目全貌介绍.md`.
- The document explains AgentMemOS from background, target scenarios, core concepts, technical architecture, major features, pgvector/RAG relationship, Redis worker operations, deployment modes, framework adapters, MCP integration, current completion status, and production gaps.
- Copied the document to the desktop for direct reading and sharing.

Verification:

- Markdown documentation generated and copied locally.

### Add worker concurrency and load testing

- Added configurable worker concurrency with `AGENTMEMOS_WORKER_CONCURRENCY`.
- `MemoryWorker` now starts multiple worker tasks when configured and reports active worker count through `/queue/status`.
- Job realtime events now include `worker_index` so concurrent worker processing can be observed in traces/SSE.
- Added `examples/load_test_events.py` to simulate concurrent `POST /events` ingestion.
- The load test reports:
  - request count
  - concurrency
  - success/failure count
  - throughput
  - average latency
  - P95 latency
  - queue status before and after the run
- Updated README with worker concurrency and load test usage.

Verification:

- `python -m py_compile agentmemos/config.py agentmemos/worker.py agentmemos/schemas.py agentmemos/main.py examples/load_test_events.py`: passed.
- `pytest -q tests/test_queue.py`: 18 passed.
- `pytest -q`: 92 passed.
- Started local AgentMemOS API on `http://127.0.0.1:8014`.
- `python examples/load_test_events.py --base-url http://127.0.0.1:8014 --requests 50 --concurrency 10 --wait-seconds 20`: passed.
  - Success: 50.
  - Failed: 0.
  - Throughput: 15.91 requests/second.
  - Average latency: 576.77 ms.
  - P95 latency: 827.51 ms.
  - Max latency: 998.41 ms.
  - Queue after run: `pending=0`, `enqueued=100`, `dequeued=100`, `completed=100`, `failed=0`, `dead_lettered=0`.

## Current System Capabilities

- Event-driven memory ingestion.
- Manual memory creation.
- Memory extraction from events.
- Scoped visibility enforcement.
- Role-aware retrieval.
- Retrieval trace explainability.
- Memory write decision traces.
- Memory status audit history.
- Memory relation governance.
- Governance-aware retrieval.
- Agent-readable memory insights.
- Automatic relation suggestions.
- Audited acceptance path for governance suggestions.
- Conservative governance agent example.
- Server-side governance pass endpoint.
- Optional background governance scheduler.
- Typed in-process job queue boundary for extraction and governance jobs.
- Dedicated governance service module.
- Repository boundary for event, memory, trace, and governance persistence access.
- Service-layer orchestration for event ingestion, memory lifecycle, and relation resolution.
- Embedding/vector retrieval boundary with default lexical retrieval preserved.
- Embedding indexing job backed by local `InMemoryVectorStore`.
- Optional vector-assisted retrieval behind disabled-by-default configuration.
- Optional Redis-backed `JobQueue` adapter with in-memory default preserved.
- Redis queue operationalization with status counters, dead-letter tracking, retry/backoff, and independent worker entrypoint.
- Redis local validation compose and smoke test for API plus independent worker flow.
- Redis pub/sub backed SSE fanout validated with real Redis E2E smoke test.
- Durable SQLite vector store option with in-memory default preserved.
- Optional Postgres/pgvector vector store for production-style shared vector indexes.
- Optional OpenAI-compatible embedding provider for production-style semantic vectors.
- Expanded Python SDK client for external agent and adapter integration.
- LangGraph-style adapter for graph/node state workflows.
- MCP-ready tool registry, route mapping, dispatcher, lightweight JSON-RPC binding, optional official FastMCP runtime, and client configuration examples.
- SSE realtime event stream for memory, job, and governance activity.
- SQLite schema compatibility guard for local MVP evolution.
- Structured rule-based extractor with auditable content signals.
- Extractor provider boundary with rule-based default and structured extraction results.
- Development dashboard for inspecting memories, events, traces, decisions, and relations.
- GitHub Actions CI for compile checks and full test suite on Python 3.11 and 3.12.

## Known Gaps

- Relation suggestions still use lexical heuristics by default; vector-assisted retrieval can use memory, SQLite, or optional pgvector storage.
- Governance, extraction, and embedding indexing use a typed job queue; Redis adapter supports status counters and dead letters, with Docker Compose available for local validation.
- SQLite remains the default local store behind thin repositories; pgvector exists for vector indexes, while full Postgres primary persistence is still pending.
- Suggestions are not applied automatically; they require explicit acceptance.
- Governance scheduling is in-process only; it is not yet backed by a durable queue or lock.
- SDK covers core APIs; LangGraph-style adapter and MCP-ready tool layer exist, while OpenAI Agents/AutoGen/CrewAI adapters are still pending.
- MCP integration has local client configuration examples, but has not yet been validated inside each external client UI.
- Redis-backed SSE fanout exists, while external client UI validation is still pending.

## Next Recommended Step

Draft the persistence and queue boundaries before swapping infrastructure:

1. Validate an end-to-end pgvector run with external embeddings enabled.
2. Validate MCP configuration inside specific external client UIs when needed.
3. Add authentication and tenant boundaries before any shared deployment.
4. Add deployment and observability documentation for Redis worker, SSE fanout, pgvector, and external model providers.

This moves the MVP toward a production-like shape without prematurely replacing the current local development stack:

`event queue -> extraction worker -> memory store -> governance job -> retrieval governance`
