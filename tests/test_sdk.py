from agentmemos import AgentMemOSClient


def test_sdk_emit_event_uses_events_endpoint():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        return {"event_id": "evt_test"}

    client = AgentMemOSClient(transport=transport)
    result = client.emit_event(
        event_type="task.created",
        task_id="task_1",
        agent_id="planner_1",
        agent_role="planner",
        content="Create the task memory plan.",
    )

    assert result["event_id"] == "evt_test"
    assert calls == [
        (
            "POST",
            "/events",
            {
                "event_type": "task.created",
                "task_id": "task_1",
                "agent_id": "planner_1",
                "agent_role": "planner",
                "content": "Create the task memory plan.",
                "metadata": {},
            },
        )
    ]


def test_sdk_retrieve_defaults_to_shared_scopes():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        return {"trace_id": "trace_test", "memories": [], "packed_context": ""}

    client = AgentMemOSClient(transport=transport)
    result = client.retrieve(
        task_id="task_1",
        agent_id="reviewer_1",
        agent_role="reviewer",
        query="approval risk",
    )

    assert result["trace_id"] == "trace_test"
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/retrieve"
    assert calls[0][2]["allowed_scopes"] == ["task-local", "team-shared", "project-global"]


def test_sdk_list_memories_builds_query_string():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        return []

    client = AgentMemOSClient(transport=transport)
    assert client.list_memories(task_id="task_1", scope="team-shared", limit=10) == []

    assert calls == [("GET", "/memories?task_id=task_1&scope=team-shared&limit=10", None)]


def test_sdk_governance_read_methods():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        if path == "/memories/mem_1":
            return {"memory_id": "mem_1"}
        if path == "/memories/mem_1/promotions":
            return [{"decision_id": "promo_1"}]
        if path == "/memories/mem_1/status-decisions":
            return [{"decision_id": "status_1"}]
        if path == "/promotions?limit=5":
            return []
        raise AssertionError(path)

    client = AgentMemOSClient(transport=transport)

    assert client.get_memory("mem_1")["memory_id"] == "mem_1"
    assert client.list_promotions(memory_id="mem_1")[0]["decision_id"] == "promo_1"
    assert client.list_status_decisions("mem_1")[0]["decision_id"] == "status_1"
    assert client.list_promotions(limit=5) == []
