import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentmemos.mcp_runtime import run_fastmcp_server


if __name__ == "__main__":
    run_fastmcp_server(
        base_url=os.environ.get("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8014"),
        transport=os.environ.get("AGENTMEMOS_MCP_TRANSPORT", "stdio"),
    )
