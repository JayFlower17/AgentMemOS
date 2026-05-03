# MCP Client Configuration Examples

These examples assume AgentMemOS is already running at `http://127.0.0.1:8014`.

## Installed Package

Use this shape after installing AgentMemOS with the optional MCP runtime:

```powershell
pip install "agentmemos[mcp]"
```

```json
{
  "mcpServers": {
    "agentmemos": {
      "command": "agentmemos-mcp",
      "env": {
        "AGENTMEMOS_BASE_URL": "http://127.0.0.1:8014"
      }
    }
  }
}
```

## Source Checkout On Windows

Use this shape when running directly from this repository:

```json
{
  "mcpServers": {
    "agentmemos": {
      "command": "python",
      "args": [
        "F:\\MemoryOS\\examples\\mcp_fastmcp_server.py"
      ],
      "env": {
        "AGENTMEMOS_BASE_URL": "http://127.0.0.1:8014"
      }
    }
  }
}
```

## Source Checkout Fallback

This fallback uses the lightweight JSON-RPC server and does not require the official MCP SDK:

```json
{
  "mcpServers": {
    "agentmemos-jsonrpc": {
      "command": "python",
      "args": [
        "F:\\MemoryOS\\examples\\mcp_stdio_server.py"
      ],
      "env": {
        "AGENTMEMOS_BASE_URL": "http://127.0.0.1:8014"
      }
    }
  }
}
```

## Tool To API Mapping

| MCP tool | AgentMemOS API |
| --- | --- |
| `agentmemos_emit_event` | `POST /events` |
| `agentmemos_retrieve` | `POST /retrieve` |
| `agentmemos_create_memory` | `POST /memories` |
| `agentmemos_list_memories` | `GET /memories` |
| `agentmemos_list_insights` | `GET /memory-insights` |
| `agentmemos_run_governance` | `POST /governance/run` |
