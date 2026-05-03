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
        if path == "/memories/mem_1/decisions":
            return [{"decision_id": "mdec_1"}]
        if path == "/memory-decisions?limit=3":
            return []
        if path == "/memories/mem_1/promotions":
            return [{"decision_id": "promo_1"}]
        if path == "/memories/mem_1/status-decisions":
            return [{"decision_id": "status_1"}]
        if path == "/promotions?limit=5":
            return []
        raise AssertionError(path)

    client = AgentMemOSClient(transport=transport)

    assert client.get_memory("mem_1")["memory_id"] == "mem_1"
    assert client.list_memory_decisions(memory_id="mem_1")[0]["decision_id"] == "mdec_1"
    assert client.list_memory_decisions(limit=3) == []
    assert client.list_promotions(memory_id="mem_1")[0]["decision_id"] == "promo_1"
    assert client.list_status_decisions("mem_1")[0]["decision_id"] == "status_1"
    assert client.list_promotions(limit=5) == []


def test_sdk_governance_action_methods():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        if path == "/governance/run":
            return {"accepted_suggestions": 1}
        if path == "/memory-insights?task_id=task_1&limit=2":
            return [{"insight_id": "insight_1"}]
        if path == "/memory-relation-suggestions?task_id=task_1&limit=4":
            return [{"suggestion_id": "suggest_1"}]
        if path == "/memory-relation-suggestions/suggest_1/accept":
            return {"relation": {"relation_id": "rel_1"}, "action": {"action_id": "gov_1"}}
        if path == "/memory-governance-actions?limit=7":
            return [{"action_id": "gov_1"}]
        if path == "/governance/scheduler":
            return {"enabled": False}
        raise AssertionError(path)

    client = AgentMemOSClient(transport=transport)

    assert client.run_governance(actor="sdk_test", max_accepts=1)["accepted_suggestions"] == 1
    assert client.list_memory_insights(task_id="task_1", limit=2)[0]["insight_id"] == "insight_1"
    assert client.list_relation_suggestions(task_id="task_1", limit=4)[0]["suggestion_id"] == "suggest_1"
    assert client.accept_relation_suggestion("suggest_1", actor="sdk_test")["relation"]["relation_id"] == "rel_1"
    assert client.list_governance_actions(limit=7)[0]["action_id"] == "gov_1"
    assert client.get_governance_scheduler()["enabled"] is False
    assert calls[0] == (
        "POST",
        "/governance/run",
        {
            "actor": "sdk_test",
            "duplicate_confidence_threshold": 0.85,
            "max_accepts": 1,
        },
    )


def test_sdk_relation_methods():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        if path == "/memory-relations":
            return {"relation_id": "rel_1"}
        if path == "/memory-relations?status_filter=open&limit=3":
            return [{"relation_id": "rel_1"}]
        if path == "/memories/mem_1/relations":
            return [{"relation_id": "rel_2"}]
        if path == "/memory-relations/rel_1/resolve":
            return {"relation_id": "rel_1", "status": "resolved"}
        raise AssertionError(path)

    client = AgentMemOSClient(transport=transport)

    assert client.create_memory_relation(
        source_memory_id="mem_1",
        target_memory_id="mem_2",
        relation_type="duplicates",
        reason="SDK test relation.",
    )["relation_id"] == "rel_1"
    assert client.list_memory_relations(status_filter="open", limit=3)[0]["relation_id"] == "rel_1"
    assert client.list_memory_relations(memory_id="mem_1")[0]["relation_id"] == "rel_2"
    assert client.resolve_memory_relation("rel_1", reason="SDK resolved.")["status"] == "resolved"
    assert calls[-1] == (
        "POST",
        "/memory-relations/rel_1/resolve",
        {"reason": "SDK resolved."},
    )


def test_sdk_event_and_trace_list_methods():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        if path == "/events?limit=2":
            return [{"event_id": "evt_1"}]
        if path == "/traces?limit=2":
            return [{"trace_id": "trace_1"}]
        if path == "/traces/trace_1":
            return {"trace_id": "trace_1"}
        raise AssertionError(path)

    client = AgentMemOSClient(transport=transport)

    assert client.list_events(limit=2)[0]["event_id"] == "evt_1"
    assert client.list_traces(limit=2)[0]["trace_id"] == "trace_1"
    assert client.get_trace("trace_1")["trace_id"] == "trace_1"
