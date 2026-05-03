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
- Durable SQLite vector store option with in-memory default preserved.
- Expanded Python SDK client for external agent and adapter integration.
- SQLite schema compatibility guard for local MVP evolution.
- Structured rule-based extractor with auditable content signals.
- Development dashboard for inspecting memories, events, traces, decisions, and relations.

## Known Gaps

- Extraction is now structured and auditable, but still rule-based; LLM-assisted extraction is pending.
- Relation suggestions and retrieval still use lexical heuristics by default; vector-assisted retrieval can be enabled locally but is not backed by pgvector yet.
- Governance, extraction, and embedding indexing use a typed job queue; Redis adapter exists but is optional and not the default.
- SQLite remains the default local store behind thin repositories; local durable vector storage exists, while Postgres/pgvector integration is still pending for production-like deployments.
- Suggestions are not applied automatically; they require explicit acceptance.
- Governance scheduling is in-process only; it is not yet backed by a durable queue or lock.
- SDK covers core APIs; external agent-framework adapters are still minimal.

## Next Recommended Step

Draft the persistence and queue boundaries before swapping infrastructure:

1. Add a LangGraph-style adapter on top of the SDK.
2. Prepare pgvector storage for shared production vector indexes.
3. Add SSE/MCP integration once the core service boundary settles.
4. Add operational documentation for Redis and SQLite vector store configuration.

This moves the MVP toward a production-like shape without prematurely replacing the current local development stack:

`event queue -> extraction worker -> memory store -> governance job -> retrieval governance`
