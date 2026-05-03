import pytest

from agentmemos import AgentMemOSClient, AgentMemOSMCPError, AgentMemOSMCPServer, AgentMemOSMCPToolbox


def test_mcp_toolbox_lists_tool_schemas():
    toolbox = AgentMemOSMCPToolbox(client=AgentMemOSClient(transport=lambda *_: {}))

    tools = toolbox.list_tools()
    names = {tool["name"] for tool in tools}

    assert "agentmemos_emit_event" in names
    assert "agentmemos_retrieve" in names
    retrieve = next(tool for tool in tools if tool["name"] == "agentmemos_retrieve")
    assert retrieve["inputSchema"]["required"] == ["task_id", "agent_id", "agent_role", "query"]


def test_mcp_retrieve_dispatches_to_sdk():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        return {"trace_id": "trace_mcp", "memories": []}

    toolbox = AgentMemOSMCPToolbox(client=AgentMemOSClient(transport=transport))
    result = toolbox.call_tool(
        "agentmemos_retrieve",
        {
            "task_id": "task_1",
            "agent_id": "coder_1",
            "agent_role": "coder",
            "query": "bounded retries",
            "allowed_scopes": ["task-local", "team-shared"],
            "limit": "4",
        },
    )

    assert result["trace_id"] == "trace_mcp"
    assert calls == [
        (
            "POST",
            "/retrieve",
            {
                "task_id": "task_1",
                "agent_id": "coder_1",
                "agent_role": "coder",
                "query": "bounded retries",
                "allowed_scopes": ["task-local", "team-shared"],
                "limit": 4,
            },
        )
    ]


def test_mcp_create_memory_dispatches_to_sdk_defaults():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        return {"memory_id": "mem_mcp"}

    toolbox = AgentMemOSMCPToolbox(client=AgentMemOSClient(transport=transport))
    result = toolbox.call_tool(
        "agentmemos_create_memory",
        {
            "memory_type": "semantic",
            "scope": "team-shared",
            "content": "Retries require bounded backoff before approval.",
        },
    )

    assert result["memory_id"] == "mem_mcp"
    assert calls[0] == (
        "POST",
        "/memories",
        {
            "task_id": None,
            "agent_id": None,
            "memory_type": "semantic",
            "scope": "team-shared",
            "content": "Retries require bounded backoff before approval.",
            "summary": None,
            "confidence": 0.75,
            "importance": 0.5,
            "source_event_id": None,
        },
    )


def test_mcp_governance_dispatches_to_sdk():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        return {"accepted_suggestions": 2}

    toolbox = AgentMemOSMCPToolbox(client=AgentMemOSClient(transport=transport))
    result = toolbox.call_tool(
        "agentmemos_run_governance",
        {
            "actor": "mcp_governor",
            "duplicate_confidence_threshold": "0.9",
            "max_accepts": "2",
        },
    )

    assert result["accepted_suggestions"] == 2
    assert calls == [
        (
            "POST",
            "/governance/run",
            {
                "actor": "mcp_governor",
                "duplicate_confidence_threshold": 0.9,
                "max_accepts": 2,
            },
        )
    ]


def test_mcp_dispatcher_rejects_unknown_or_missing_arguments():
    toolbox = AgentMemOSMCPToolbox(client=AgentMemOSClient(transport=lambda *_: {}))

    with pytest.raises(AgentMemOSMCPError, match="Unknown AgentMemOS MCP tool"):
        toolbox.call_tool("unknown_tool", {})

    with pytest.raises(AgentMemOSMCPError, match="Missing required argument: query"):
        toolbox.call_tool(
            "agentmemos_retrieve",
            {"task_id": "task_1", "agent_id": "coder_1", "agent_role": "coder"},
        )


def test_mcp_server_handles_tool_list_and_call():
    def transport(method, path, payload):
        assert method == "POST"
        assert path == "/retrieve"
        return {"trace_id": "trace_server", "memories": []}

    toolbox = AgentMemOSMCPToolbox(client=AgentMemOSClient(transport=transport))
    server = AgentMemOSMCPServer(toolbox=toolbox)

    listed = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listed["result"]["tools"][0]["name"].startswith("agentmemos_")

    called = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "agentmemos_retrieve",
                "arguments": {
                    "task_id": "task_1",
                    "agent_id": "coder_1",
                    "agent_role": "coder",
                    "query": "retry",
                },
            },
        }
    )
    assert called["result"]["content"][0]["type"] == "text"
    assert "trace_server" in called["result"]["content"][0]["text"]


def test_mcp_server_returns_json_rpc_errors():
    server = AgentMemOSMCPServer(toolbox=AgentMemOSMCPToolbox(client=AgentMemOSClient(transport=lambda *_: {})))

    unknown = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "missing/method"})
    assert unknown["error"]["code"] == -32601

    invalid = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {}})
    assert invalid["error"]["code"] == -32602
