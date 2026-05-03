from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentmemos.sdk import AgentMemOSClient


class AgentMemOSMCPError(ValueError):
    """Raised when an AgentMemOS MCP tool call cannot be dispatched."""


JsonObject = dict[str, Any]


def _object_schema(properties: JsonObject, required: list[str] | None = None) -> JsonObject:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


AGENTMEMOS_MCP_TOOLS: list[JsonObject] = [
    {
        "name": "agentmemos_emit_event",
        "description": "Record an agent event and let AgentMemOS extract useful memories asynchronously.",
        "inputSchema": _object_schema(
            {
                "event_type": {"type": "string"},
                "task_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "agent_role": {"type": "string"},
                "content": {"type": "string"},
                "metadata": {"type": "object"},
            },
            ["event_type", "task_id", "agent_id", "agent_role", "content"],
        ),
    },
    {
        "name": "agentmemos_retrieve",
        "description": "Retrieve scoped, role-aware memories for an agent before it acts.",
        "inputSchema": _object_schema(
            {
                "task_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "agent_role": {"type": "string"},
                "query": {"type": "string"},
                "allowed_scopes": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            ["task_id", "agent_id", "agent_role", "query"],
        ),
    },
    {
        "name": "agentmemos_create_memory",
        "description": "Create an explicit AgentMemOS memory when an agent or user decides something should persist.",
        "inputSchema": _object_schema(
            {
                "memory_type": {"type": "string"},
                "scope": {"type": "string"},
                "content": {"type": "string"},
                "task_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "summary": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "importance": {"type": "number", "minimum": 0, "maximum": 1},
                "source_event_id": {"type": "string"},
            },
            ["memory_type", "scope", "content"],
        ),
    },
    {
        "name": "agentmemos_list_memories",
        "description": "List memories for inspection or agent planning, optionally filtered by task, scope, or type.",
        "inputSchema": _object_schema(
            {
                "task_id": {"type": "string"},
                "scope": {"type": "string"},
                "memory_type": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            }
        ),
    },
    {
        "name": "agentmemos_list_insights",
        "description": "List governance insights that summarize memory quality, duplicates, and lifecycle signals.",
        "inputSchema": _object_schema(
            {
                "task_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            }
        ),
    },
    {
        "name": "agentmemos_run_governance",
        "description": "Run a governance pass to create insights, relation suggestions, and accepted governance actions.",
        "inputSchema": _object_schema(
            {
                "actor": {"type": "string"},
                "duplicate_confidence_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                "max_accepts": {"type": "integer", "minimum": 0, "maximum": 100},
            }
        ),
    },
]


def _required(arguments: JsonObject, key: str) -> Any:
    value = arguments.get(key)
    if value is None or value == "":
        raise AgentMemOSMCPError(f"Missing required argument: {key}")
    return value


def _int_arg(arguments: JsonObject, key: str, default: int) -> int:
    value = arguments.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AgentMemOSMCPError(f"Argument {key} must be an integer") from exc


def _float_arg(arguments: JsonObject, key: str, default: float) -> float:
    value = arguments.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AgentMemOSMCPError(f"Argument {key} must be a number") from exc


@dataclass
class AgentMemOSMCPToolbox:
    """MCP-ready tool registry and dispatcher backed by the AgentMemOS SDK."""

    client: AgentMemOSClient = field(default_factory=AgentMemOSClient)

    def list_tools(self) -> list[JsonObject]:
        return list(AGENTMEMOS_MCP_TOOLS)

    def call_tool(self, name: str, arguments: JsonObject | None = None) -> Any:
        arguments = arguments or {}
        handlers = {
            "agentmemos_emit_event": self._emit_event,
            "agentmemos_retrieve": self._retrieve,
            "agentmemos_create_memory": self._create_memory,
            "agentmemos_list_memories": self._list_memories,
            "agentmemos_list_insights": self._list_insights,
            "agentmemos_run_governance": self._run_governance,
        }
        handler = handlers.get(name)
        if handler is None:
            raise AgentMemOSMCPError(f"Unknown AgentMemOS MCP tool: {name}")
        return handler(arguments)

    def _emit_event(self, arguments: JsonObject) -> Any:
        return self.client.emit_event(
            event_type=_required(arguments, "event_type"),
            task_id=_required(arguments, "task_id"),
            agent_id=_required(arguments, "agent_id"),
            agent_role=_required(arguments, "agent_role"),
            content=_required(arguments, "content"),
            metadata=arguments.get("metadata") or {},
        )

    def _retrieve(self, arguments: JsonObject) -> Any:
        return self.client.retrieve(
            task_id=_required(arguments, "task_id"),
            agent_id=_required(arguments, "agent_id"),
            agent_role=_required(arguments, "agent_role"),
            query=_required(arguments, "query"),
            allowed_scopes=arguments.get("allowed_scopes"),
            limit=_int_arg(arguments, "limit", 8),
        )

    def _create_memory(self, arguments: JsonObject) -> Any:
        return self.client.create_memory(
            memory_type=_required(arguments, "memory_type"),
            scope=_required(arguments, "scope"),
            content=_required(arguments, "content"),
            task_id=arguments.get("task_id"),
            agent_id=arguments.get("agent_id"),
            summary=arguments.get("summary"),
            confidence=_float_arg(arguments, "confidence", 0.75),
            importance=_float_arg(arguments, "importance", 0.5),
            source_event_id=arguments.get("source_event_id"),
        )

    def _list_memories(self, arguments: JsonObject) -> Any:
        return self.client.list_memories(
            task_id=arguments.get("task_id"),
            scope=arguments.get("scope"),
            memory_type=arguments.get("memory_type"),
            limit=_int_arg(arguments, "limit", 100),
        )

    def _list_insights(self, arguments: JsonObject) -> Any:
        return self.client.list_memory_insights(
            task_id=arguments.get("task_id"),
            limit=_int_arg(arguments, "limit", 50),
        )

    def _run_governance(self, arguments: JsonObject) -> Any:
        return self.client.run_governance(
            actor=arguments.get("actor", "mcp_tool"),
            duplicate_confidence_threshold=_float_arg(arguments, "duplicate_confidence_threshold", 0.85),
            max_accepts=_int_arg(arguments, "max_accepts", 10),
        )


def build_default_toolbox(base_url: str = "http://127.0.0.1:8014") -> AgentMemOSMCPToolbox:
    return AgentMemOSMCPToolbox(client=AgentMemOSClient(base_url=base_url))
