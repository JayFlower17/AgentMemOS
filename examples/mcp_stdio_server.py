import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentmemos import AgentMemOSClient, AgentMemOSMCPServer, AgentMemOSMCPToolbox


def main() -> None:
    base_url = os.environ.get("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8014")
    toolbox = AgentMemOSMCPToolbox(client=AgentMemOSClient(base_url=base_url))
    AgentMemOSMCPServer(toolbox=toolbox).serve_json_lines()


if __name__ == "__main__":
    main()
