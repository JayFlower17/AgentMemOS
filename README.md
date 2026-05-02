# AgentMemOS

Event-driven scoped memory infrastructure for multi-agent workflows.

This MVP implements the first closed loop from the project plan:

1. Agents submit events to `POST /events`.
2. A background worker extracts structured memory records.
3. Memories are persisted in SQLite by default.
4. Retrieval returns role-aware scoped context through `POST /retrieve`.
5. Every retrieval writes an auditable trace, available at `GET /traces/{trace_id}`.

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

## Core Endpoints

- `POST /events` ingests an agent runtime event and queues memory extraction.
- `POST /memories` creates an explicit memory record.
- `POST /retrieve` returns scoped, role-aware memory context and stores a retrieval trace.
- `POST /memories/{memory_id}/promote` promotes a memory to a broader scope.
- `GET /memories/{memory_id}` returns one memory record.
- `GET /memories/{memory_id}/promotions` returns promotion history for a memory.
- `POST /memories/{memory_id}/status` archives or restores a memory with a reason.
- `GET /memories/{memory_id}/status-decisions` returns status change history for a memory.
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
