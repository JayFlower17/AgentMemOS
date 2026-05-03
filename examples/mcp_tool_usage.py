import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentmemos import build_default_toolbox


def main() -> None:
    base_url = os.environ.get("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8014")
    toolbox = build_default_toolbox(base_url)

    print("tools:")
    for tool in toolbox.list_tools():
        print("-", tool["name"])

    result = toolbox.call_tool(
        "agentmemos_retrieve",
        {
            "task_id": "task_sdk_demo",
            "agent_id": "mcp_client_1",
            "agent_role": "coder",
            "query": "retry approval and governance",
            "limit": 3,
        },
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
