from __future__ import annotations

import os
from typing import Any

from agentmemos.mcp_tools import AgentMemOSMCPToolbox, build_default_toolbox


class AgentMemOSMCPRuntimeUnavailable(ImportError):
    """Raised when the optional official MCP SDK is not installed."""


def _register_fastmcp_tools(mcp: Any, toolbox: AgentMemOSMCPToolbox) -> Any:
    @mcp.tool()
    def agentmemos_emit_event(
        event_type: str,
        task_id: str,
        agent_id: str,
        agent_role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record an agent event and let AgentMemOS extract useful memories asynchronously."""
        return toolbox.call_tool(
            "agentmemos_emit_event",
            {
                "event_type": event_type,
                "task_id": task_id,
                "agent_id": agent_id,
                "agent_role": agent_role,
                "content": content,
                "metadata": metadata or {},
            },
        )

    @mcp.tool()
    def agentmemos_retrieve(
        task_id: str,
        agent_id: str,
        agent_role: str,
        query: str,
        allowed_scopes: list[str] | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Retrieve scoped, role-aware memories for an agent before it acts."""
        return toolbox.call_tool(
            "agentmemos_retrieve",
            {
                "task_id": task_id,
                "agent_id": agent_id,
                "agent_role": agent_role,
                "query": query,
                "allowed_scopes": allowed_scopes,
                "limit": limit,
            },
        )

    @mcp.tool()
    def agentmemos_create_memory(
        memory_type: str,
        scope: str,
        content: str,
        task_id: str | None = None,
        agent_id: str | None = None,
        summary: str | None = None,
        confidence: float = 0.75,
        importance: float = 0.5,
        source_event_id: str | None = None,
    ) -> dict[str, Any]:
        """Create an explicit AgentMemOS memory when something should persist."""
        return toolbox.call_tool(
            "agentmemos_create_memory",
            {
                "memory_type": memory_type,
                "scope": scope,
                "content": content,
                "task_id": task_id,
                "agent_id": agent_id,
                "summary": summary,
                "confidence": confidence,
                "importance": importance,
                "source_event_id": source_event_id,
            },
        )

    @mcp.tool()
    def agentmemos_list_memories(
        task_id: str | None = None,
        scope: str | None = None,
        memory_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List memories, optionally filtered by task, scope, or memory type."""
        return toolbox.call_tool(
            "agentmemos_list_memories",
            {
                "task_id": task_id,
                "scope": scope,
                "memory_type": memory_type,
                "limit": limit,
            },
        )

    @mcp.tool()
    def agentmemos_list_insights(task_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """List governance insights about memory quality, duplicates, and lifecycle signals."""
        return toolbox.call_tool("agentmemos_list_insights", {"task_id": task_id, "limit": limit})

    @mcp.tool()
    def agentmemos_run_governance(
        actor: str = "official_mcp_runtime",
        duplicate_confidence_threshold: float = 0.85,
        max_accepts: int = 10,
    ) -> dict[str, Any]:
        """Run a conservative governance pass over AgentMemOS memories."""
        return toolbox.call_tool(
            "agentmemos_run_governance",
            {
                "actor": actor,
                "duplicate_confidence_threshold": duplicate_confidence_threshold,
                "max_accepts": max_accepts,
            },
        )

    return mcp


def create_fastmcp_server(
    toolbox: AgentMemOSMCPToolbox | None = None,
    *,
    base_url: str = "http://127.0.0.1:8014",
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise AgentMemOSMCPRuntimeUnavailable(
            'The official MCP SDK is not installed. Install with: pip install "agentmemos[mcp]"'
        ) from exc

    mcp = FastMCP(
        "AgentMemOS",
        instructions=(
            "AgentMemOS exposes scoped, role-aware multi-agent memory tools for event ingestion, "
            "retrieval, manual memory creation, and governance."
        ),
        json_response=True,
    )
    return _register_fastmcp_tools(mcp, toolbox or build_default_toolbox(base_url))


def run_fastmcp_server(
    *,
    base_url: str | None = None,
    transport: str | None = None,
) -> None:
    resolved_base_url = base_url or os.environ.get("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8014")
    resolved_transport = transport or os.environ.get("AGENTMEMOS_MCP_TRANSPORT", "stdio")
    create_fastmcp_server(base_url=resolved_base_url).run(transport=resolved_transport)


def main() -> None:
    run_fastmcp_server()


if __name__ == "__main__":
    main()
