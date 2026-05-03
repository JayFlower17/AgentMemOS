import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentmemos import AgentMemOSClient, AgentMemOSMCPServer, AgentMemOSMCPToolbox


def main() -> None:
    base_url = os.environ.get("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8014")
    server = AgentMemOSMCPServer(toolbox=AgentMemOSMCPToolbox(client=AgentMemOSClient(base_url=base_url)))

    tools_response = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tool_names = [tool["name"] for tool in tools_response["result"]["tools"]]
    print("tools:", ", ".join(tool_names))

    call_response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "agentmemos_retrieve",
                "arguments": {
                    "task_id": "task_sdk_demo",
                    "agent_id": "mcp_smoke_1",
                    "agent_role": "coder",
                    "query": "retry approval memory",
                    "limit": 3,
                },
            },
        }
    )
    print(json.dumps(call_response, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
