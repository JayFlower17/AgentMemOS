from agentmemos import AgentMemOSClient
from agentmemos.adapters import LangGraphMemoryAdapter, MemoryStepAdapter


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


def test_langgraph_memory_adapter_before_and_after_node():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        if path == "/retrieve":
            return {
                "trace_id": "trace_langgraph",
                "memories": [],
                "packed_context": "- [team-shared/procedural] Use bounded retry backoff.",
            }
        if path == "/events":
            return {"event_id": "evt_langgraph"}
        raise AssertionError(path)

    adapter = LangGraphMemoryAdapter(
        client=AgentMemOSClient(transport=transport),
        agent_id="coder_1",
        agent_role="coder",
    )

    before = adapter.before_node({"task_id": "task_1", "current_goal": "retry implementation"})
    assert before["memory_context"] == "- [team-shared/procedural] Use bounded retry backoff."
    assert before["memory_trace_id"] == "trace_langgraph"

    after = adapter.after_node(before, {**before, "result": "implemented retry"})
    assert after["result"] == "implemented retry"
    assert calls[1] == (
        "POST",
        "/events",
        {
            "event_type": "subtask.completed",
            "task_id": "task_1",
            "agent_id": "coder_1",
            "agent_role": "coder",
            "content": "implemented retry",
            "metadata": {
                "memory_trace_id": "trace_langgraph",
                "adapter": "LangGraphMemoryAdapter",
            },
        },
    )


def test_langgraph_memory_adapter_wrap_node():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        if path == "/retrieve":
            return {"trace_id": "trace_wrapped", "memories": [], "packed_context": "memory ctx"}
        if path == "/events":
            return {"event_id": "evt_wrapped"}
        raise AssertionError(path)

    adapter = LangGraphMemoryAdapter(
        client=AgentMemOSClient(transport=transport),
        agent_id="reviewer_1",
        agent_role="reviewer",
        event_type="review.finding.created",
    )

    def node(state):
        assert state["memory_context"] == "memory ctx"
        return {**state, "message": "Reviewer found approval risk."}

    result = adapter.wrap_node(node)({"task_id": "task_2", "query": "approval"})

    assert result["memory_trace_id"] == "trace_wrapped"
    assert calls[1][2]["event_type"] == "review.finding.created"
    assert calls[1][2]["content"] == "Reviewer found approval risk."
