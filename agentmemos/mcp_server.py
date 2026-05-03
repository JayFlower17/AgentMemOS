from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, TextIO

from agentmemos.mcp_tools import AgentMemOSMCPError, AgentMemOSMCPToolbox, build_default_toolbox


JsonObject = dict[str, Any]


@dataclass
class AgentMemOSMCPServer:
    """Small JSON-RPC binding for AgentMemOS MCP-style tools.

    This keeps protocol handling separate from memory behavior. A full MCP runtime can
    replace this transport layer while continuing to use AgentMemOSMCPToolbox.
    """

    toolbox: AgentMemOSMCPToolbox = field(default_factory=build_default_toolbox)
    protocol_version: str = "2024-11-05"

    def handle_request(self, request: JsonObject) -> JsonObject | None:
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        if request_id is None:
            return None

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": self.protocol_version,
                    "serverInfo": {"name": "agentmemos", "version": "0.1.0"},
                    "capabilities": {"tools": {"listChanged": False}},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.toolbox.list_tools()}
            elif method == "tools/call":
                result = self._call_tool(params)
            else:
                return self._error(request_id, -32601, f"Method not found: {method}")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except AgentMemOSMCPError as exc:
            return self._error(request_id, -32602, str(exc))
        except Exception as exc:
            return self._error(request_id, -32603, f"Internal AgentMemOS MCP error: {exc}")

    def _call_tool(self, params: JsonObject) -> JsonObject:
        name = params.get("name")
        if not name:
            raise AgentMemOSMCPError("Missing required argument: name")
        result = self.toolbox.call_tool(name, params.get("arguments") or {})
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False),
                }
            ]
        }

    def _error(self, request_id: Any, code: int, message: str) -> JsonObject:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def serve_json_lines(self, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            response = self.handle_request(json.loads(line))
            if response is not None:
                stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                stdout.flush()


def main() -> None:
    AgentMemOSMCPServer().serve_json_lines()


if __name__ == "__main__":
    main()
