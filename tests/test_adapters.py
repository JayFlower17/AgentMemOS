from agentmemos import AgentMemOSClient
from agentmemos.adapters import MemoryStepAdapter


def test_memory_step_adapter_injects_context_and_emits_event():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        if path == "/retrieve":
            return {
                "trace_id": "trace_123",
                "memories": [],
                "packed_context": "- [team-shared/episodic] Check retry backoff.",
            }
        if path == "/events":
            return {"event_id": "evt_123"}
        raise AssertionError(path)

    client = AgentMemOSClient(transport=transport)
    adapter = MemoryStepAdapter(client=client, agent_id="coder_1", agent_role="coder")

    def step(state):
        assert state["memory_context"] == "- [team-shared/episodic] Check retry backoff."
        assert state["memory_trace_id"] == "trace_123"
        return {**state, "result": "done"}

    wrapped = adapter.wrap(step)
    result = wrapped({"task_id": "task_1", "current_goal": "retry implementation"})

    assert result["result"] == "done"
    assert calls[0] == (
        "POST",
        "/retrieve",
        {
            "task_id": "task_1",
            "agent_id": "coder_1",
            "agent_role": "coder",
            "query": "retry implementation",
            "allowed_scopes": ["task-local", "team-shared", "project-global"],
            "limit": 8,
        },
    )
    assert calls[1][0] == "POST"
    assert calls[1][1] == "/events"
    assert calls[1][2]["event_type"] == "subtask.completed"
    assert calls[1][2]["metadata"]["memory_trace_id"] == "trace_123"


def test_memory_step_adapter_requires_task_id():
    adapter = MemoryStepAdapter(client=AgentMemOSClient(transport=lambda *args: {}), agent_id="a", agent_role="coder")
    wrapped = adapter.wrap(lambda state: state)

    try:
        wrapped({"current_goal": "missing task"})
    except ValueError as exc:
        assert "task_id" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
