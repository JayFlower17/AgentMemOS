# AgentMemOS

Event-driven scoped memory infrastructure for multi-agent workflows.

CI runs on pushes to `JayFlower`, `main`, and `master`, and on pull requests. It compiles the source and runs the full pytest suite on Python 3.11 and 3.12.

This MVP implements the first closed loop from the project plan:

1. Agents submit events to `POST /events`.
2. A background worker extracts structured memory records.
3. Memories are persisted in SQLite by default.
4. Retrieval returns role-aware scoped context through `POST /retrieve`.
5. Every memory write records why it was classified, scoped, and scored.
6. Duplicate writes reuse the matching active memory and add a `deduplicated` decision trace.
7. Memory governance relations mark superseded, conflicting, and duplicate memories.
8. Every retrieval applies memory governance and writes an auditable trace with selected memories, filtered memories, scores, open relation warnings, and reasons, available at `GET /traces/{trace_id}`.

The default setup is intentionally light: no Postgres or Redis is required for local development. The app is structured so those can be added behind the storage and queue boundaries later.

## Run

```powershell
python -m uvicorn agentmemos.main:app --reload
```

Open:

- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Try The Demo

With the server running:

```powershell
python examples/demo_flow.py
```

If your API is running on another port:

```powershell
$env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8010"; python examples/demo_flow.py
```

## Python SDK

External agent runtimes can integrate with AgentMemOS through two calls:

```python
from agentmemos import AgentMemOSClient

memory = AgentMemOSClient("http://127.0.0.1:8010")

context = memory.retrieve(
    task_id="task_123",
    agent_id="coder_1",
    agent_role="coder",
    query="Implement retry logic safely",
)

memory.emit_event(
    event_type="tool.result.observed",
    task_id="task_123",
    agent_id="coder_1",
    agent_role="coder",
    content="Tests failed because retry backoff exceeded the timeout.",
)
```

With the server running:

```powershell
$env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8010"; python examples/sdk_usage.py
```

## Memory Extraction

AgentMemOS uses an extractor provider to decide whether an event should become memory and how it should be classified.

The default extractor is local and rule-based:

```powershell
$env:AGENTMEMOS_EXTRACTOR_BACKEND="rule"
```

It returns a structured extraction result with:

- `should_write`
- memory type
- scope
- summary
- confidence
- importance
- reason
- auditable signals

The provider boundary is designed so an optional LLM extractor can be added later without replacing the local default.

OpenAI-compatible extractor can be enabled with:

```powershell
$env:AGENTMEMOS_EXTRACTOR_BACKEND="openai"
$env:AGENTMEMOS_OPENAI_API_KEY="..."
$env:AGENTMEMOS_OPENAI_BASE_URL="https://api.openai.com/v1"
$env:AGENTMEMOS_OPENAI_EXTRACTOR_MODEL="gpt-4o-mini"
```

You can also point to a local key file that is not committed:

```powershell
$env:AGENTMEMOS_OPENAI_API_KEY_FILE="C:\path\to\LLM-API-KEY.txt"
```

If the file contains multiple labeled keys, set:

```powershell
$env:AGENTMEMOS_OPENAI_API_KEY_LABEL="DeepSeek"
```

For DeepSeek-compatible testing:

```powershell
$env:AGENTMEMOS_OPENAI_BASE_URL="https://api.deepseek.com/v1"
$env:AGENTMEMOS_OPENAI_EXTRACTOR_MODEL="deepseek-chat"
```

Run the extractor smoke test:

```powershell
python examples/openai_extractor_smoke.py
```

## Governance Agent Example

Run the conservative governance agent loop against a running server:

```powershell
$env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8014"; python examples/governance_agent.py
```

The example fetches memory insights and relation suggestions, accepts only high-confidence duplicate suggestions, and leaves conflicts for explicit review.
By default it accepts at most 10 suggestions per run. Override with `AGENTMEMOS_GOVERNANCE_MAX_ACCEPTS`.

Governance suggestions are rule/similarity-based by default. An OpenAI-compatible LLM reviewer can be enabled to add semantic suggestions, but it only proposes relations and never mutates memory state directly:

```powershell
$env:AGENTMEMOS_GOVERNANCE_REVIEWER_BACKEND="openai"
$env:AGENTMEMOS_OPENAI_API_KEY="..."
$env:AGENTMEMOS_OPENAI_BASE_URL="https://api.openai.com/v1"
$env:AGENTMEMOS_OPENAI_GOVERNANCE_MODEL="gpt-4o-mini"
$env:AGENTMEMOS_GOVERNANCE_REVIEWER_MAX_PAIRS="25"
$env:AGENTMEMOS_GOVERNANCE_REVIEWER_MIN_CONFIDENCE="0.7"
```

The LLM reviewer can suggest `duplicates`, `conflicts_with`, or `supersedes`. Suggestions still require acceptance through the governance API or governance pass policy, and accepted actions are written to the governance audit log.

## Generic Agent Step Adapter

Use the framework-agnostic adapter to wrap any dict-in, dict-out agent step:

```python
from agentmemos import AgentMemOSClient
from agentmemos.adapters import MemoryStepAdapter

def coder_step(state):
    prompt_context = state["memory_context"]
    return {**state, "result": "implemented retry handling"}

client = AgentMemOSClient("http://127.0.0.1:8010")
wrapped_step = MemoryStepAdapter(
    client=client,
    agent_id="coder_1",
    agent_role="coder",
).wrap(coder_step)

result = wrapped_step({
    "task_id": "task_123",
    "current_goal": "Implement retry logic safely",
})
```

The adapter retrieves role-aware memory before the step and emits a completion event after the step.

## MCP Integration

AgentMemOS can be exposed as MCP tools for external agent clients.

The lightweight JSON-RPC binding has no extra dependency:

```powershell
$env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8014"; python examples/mcp_stdio_server.py
```

For the official MCP Python SDK runtime, install the optional dependency and run the FastMCP entrypoint:

```powershell
pip install "agentmemos[mcp]"
$env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8014"; python examples/mcp_fastmcp_server.py
```

When installed as a package, the official runtime is also available as a console command:

```powershell
$env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8014"; agentmemos-mcp
```

The official runtime defaults to stdio transport. Use streamable HTTP by setting:

```powershell
$env:AGENTMEMOS_MCP_TRANSPORT="streamable-http"; python examples/mcp_fastmcp_server.py
```

Current MCP tools:

- `agentmemos_emit_event`
- `agentmemos_retrieve`
- `agentmemos_create_memory`
- `agentmemos_list_memories`
- `agentmemos_list_insights`
- `agentmemos_run_governance`

Client configuration examples are available in `examples/mcp_client_configs.md`.

Run a local smoke test against a running AgentMemOS service:

```powershell
$env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8014"; python examples/mcp_smoke_test.py
```

Tool to API mapping:

| MCP tool | AgentMemOS API |
| --- | --- |
| `agentmemos_emit_event` | `POST /events` |
| `agentmemos_retrieve` | `POST /retrieve` |
| `agentmemos_create_memory` | `POST /memories` |
| `agentmemos_list_memories` | `GET /memories` |
| `agentmemos_list_insights` | `GET /memory-insights` |
| `agentmemos_run_governance` | `POST /governance/run` |

## Realtime Events

AgentMemOS exposes a lightweight Server-Sent Events stream for local realtime monitoring:

```powershell
$env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8014"; python examples/sse_watch.py
```

Or subscribe directly:

```text
GET /events/stream?replay=10
Accept: text/event-stream
```

The stream emits events such as:

- `agent_event.ingested`
- `job.enqueued`
- `job.started`
- `job.completed`
- `job.failed`
- `memory.created`
- `memory.extracted`
- `memory.embedded`
- `memory.promoted`
- `memory.status_updated`
- `memory_relation.created`
- `memory_relation.resolved`
- `governance.completed`
- `governance.suggestion_accepted`

For multi-process API/worker setups, enable Redis fanout so worker-published events are visible to API SSE subscribers:

```powershell
$env:AGENTMEMOS_REDIS_EVENT_FANOUT_ENABLED="true"
$env:AGENTMEMOS_REDIS_EVENT_CHANNEL="agentmemos:events"
```

## Queue And Worker Operations

Local development still defaults to an in-process memory queue and an API-owned worker.
Start Redis locally with Docker Compose:

```powershell
docker compose -f docker-compose.redis.yml up -d
docker compose -f docker-compose.redis.yml ps
```

For Redis-backed queue operation:

```powershell
$env:AGENTMEMOS_JOB_QUEUE_BACKEND="redis"
$env:AGENTMEMOS_REDIS_URL="redis://localhost:6379/0"
$env:AGENTMEMOS_REDIS_QUEUE_NAME="agentmemos:jobs"
python -m uvicorn agentmemos.main:app --host 127.0.0.1 --port 8014
```

To run workers as an independent process, disable the API-owned worker and start `agentmemos-worker`:

```powershell
$env:AGENTMEMOS_API_WORKER_ENABLED="false"
$env:AGENTMEMOS_JOB_QUEUE_BACKEND="redis"
python -m uvicorn agentmemos.main:app --host 127.0.0.1 --port 8014
```

In another terminal:

```powershell
$env:AGENTMEMOS_JOB_QUEUE_BACKEND="redis"
python -m agentmemos.worker_app
```

If AgentMemOS is installed as a package, use `agentmemos-worker` instead.

Retry behavior is configurable:

```powershell
$env:AGENTMEMOS_JOB_MAX_ATTEMPTS="3"
$env:AGENTMEMOS_JOB_RETRY_BACKOFF_SECONDS="1"
$env:AGENTMEMOS_WORKER_CONCURRENCY="4"
```

Inspect queue status:

```text
GET /queue/status
```

Run a Redis queue smoke test after starting Redis, the API, and one worker:

```powershell
$env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8014"; python examples/redis_queue_smoke_test.py
```

Or run the full local E2E smoke test, which starts API-only mode and an independent worker for you:

```powershell
$env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8014"; python examples/redis_queue_e2e_smoke.py
```

The E2E runner also enables Redis-backed SSE fanout and verifies worker events are visible through `/events/stream`.

Run a lightweight concurrent event ingestion load test against a running API:

```powershell
$env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8014"; python examples/load_test_events.py --requests 100 --concurrency 20
```

The load test reports success count, failure count, throughput, average latency, P95 latency, and queue status before/after the run. It is intended as a concurrency-readiness smoke test, not a replacement for full production benchmarking.

Stop Redis when finished:

```powershell
docker compose -f docker-compose.redis.yml down
```

## Pgvector Storage

Local vector retrieval defaults to in-memory or SQLite-backed embeddings.
The default embedding provider is local hashing, which needs no API key:

```powershell
$env:AGENTMEMOS_EMBEDDING_PROVIDER="hashing"
```

OpenAI-compatible embedding APIs can be enabled without changing the worker or retrieval code:

```powershell
$env:AGENTMEMOS_EMBEDDING_PROVIDER="openai"
$env:AGENTMEMOS_OPENAI_EMBEDDING_API_KEY="..."
$env:AGENTMEMOS_OPENAI_EMBEDDING_BASE_URL="https://api.openai.com/v1"
$env:AGENTMEMOS_OPENAI_EMBEDDING_MODEL="text-embedding-3-small"
```

For a labeled key file, set the label explicitly:

```powershell
$env:AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_FILE="C:\path\to\LLM-API-KEY.txt"
$env:AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_LABEL="Embedding"
```

For the local third-party OpenAI-compatible provider used during development:

```powershell
$env:AGENTMEMOS_EMBEDDING_PROVIDER="openai"
$env:AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_FILE="$HOME\Desktop\LLM-API-KEY.txt"
$env:AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_LABEL="Embedding"
$env:AGENTMEMOS_OPENAI_EMBEDDING_BASE_URL="https://api.jiekou.ai/openai"
$env:AGENTMEMOS_OPENAI_EMBEDDING_MODEL="text-embedding-3-large"
python examples/openai_embedding_smoke.py
```

If pgvector is used with external embeddings, `AGENTMEMOS_PGVECTOR_DIMENSIONS` must match the embedding dimensions returned by the provider. For native `text-embedding-3-large` embeddings this is usually `3072`; if the provider supports a custom dimensions parameter, set `AGENTMEMOS_OPENAI_EMBEDDING_DIMENSIONS` and use the same value for pgvector.

For Postgres/pgvector validation, start pgvector locally:

```powershell
docker compose -f docker-compose.pgvector.yml up -d
docker compose -f docker-compose.pgvector.yml ps
```

Then run AgentMemOS with pgvector enabled:

```powershell
$env:AGENTMEMOS_VECTOR_STORE_BACKEND="pgvector"
$env:AGENTMEMOS_PGVECTOR_URL="postgresql://agentmemos:agentmemos@localhost:5432/agentmemos"
$env:AGENTMEMOS_PGVECTOR_DIMENSIONS="64"
$env:AGENTMEMOS_VECTOR_RETRIEVAL_ENABLED="true"
$env:AGENTMEMOS_VECTOR_RETRIEVAL_WEIGHT="0.1"
python -m uvicorn agentmemos.main:app --host 127.0.0.1 --port 8014
```

Run a pgvector smoke test:

```powershell
$env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8014"; python examples/pgvector_smoke_test.py
```

Or run the full local E2E smoke test, which starts an API process with pgvector enabled:

```powershell
$env:AGENTMEMOS_BASE_URL="http://127.0.0.1:8014"; python examples/pgvector_e2e_smoke.py
```

Stop pgvector when finished:

```powershell
docker compose -f docker-compose.pgvector.yml down
```

## Core Endpoints

- `POST /events` ingests an agent runtime event and queues memory extraction.
- `GET /events/stream` streams realtime memory, job, and governance events through SSE.
- `GET /queue/status` returns queue depth, worker state, retry settings, and dead-letter counters.
- `POST /memories` creates an explicit memory record.
- `POST /retrieve` returns scoped, role-aware memory context and stores a retrieval trace.
- `POST /memories/{memory_id}/promote` promotes a memory to a broader scope.
- `GET /memories/{memory_id}` returns one memory record.
- `GET /memories/{memory_id}/decisions` returns write/classification decisions for a memory.
- `GET /memories/{memory_id}/promotions` returns promotion history for a memory.
- `POST /memories/{memory_id}/status` archives or restores a memory with a reason.
- `GET /memories/{memory_id}/status-decisions` returns status change history for a memory.
- `POST /memory-relations` records governance links such as `supersedes`, `conflicts_with`, and `duplicates`.
- `GET /memory-relations` returns recent memory governance links.
- `GET /memories/{memory_id}/relations` returns governance links for one memory.
- `POST /memory-relations/{relation_id}/resolve` closes a reviewed governance link.
- `GET /memory-relation-suggestions` proposes duplicate or conflict relations between active memories.
- `POST /memory-relation-suggestions/{suggestion_id}/accept` creates a relation from a still-valid suggestion.
- `POST /governance/run` runs a conservative governance pass that can accept high-confidence duplicate suggestions.
- `GET /memory-governance-actions` returns audited governance actions.
- `GET /memory-insights` returns agent-readable governance action items from open relations and retrieval traces.
- `GET /memory-decisions` returns recent memory write decisions.
- `GET /promotions` returns recent promotion decisions.
- `GET /traces/{trace_id}` returns an audit trace for a retrieval.

## Example Retrieval Request

```json
{
  "task_id": "task_123",
  "agent_id": "reviewer_1",
  "agent_role": "reviewer",
  "query": "Review the latest implementation risks",
  "allowed_scopes": ["task-local", "team-shared", "project-global"]
}
```
