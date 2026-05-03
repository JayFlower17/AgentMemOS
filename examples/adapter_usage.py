import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentmemos import AgentMemOSClient
from agentmemos.adapters import LangGraphMemoryAdapter, MemoryStepAdapter


def coder_step(state):
    memory_context = state.get("memory_context", "")
    return {
        **state,
        "result": f"Implemented bounded retry handling with memory context: {memory_context[:80]}",
    }


def main() -> None:
    client = AgentMemOSClient("http://127.0.0.1:8014")
    adapter = MemoryStepAdapter(client=client, agent_id="coder_1", agent_role="coder")
    wrapped_step = adapter.wrap(coder_step)

    result = wrapped_step(
        {
            "task_id": "task_sdk_demo",
            "current_goal": "Implement bounded retry handling safely.",
        }
    )

    print("trace:", result["memory_trace_id"])
    print("result:", result["result"])

    graph_adapter = LangGraphMemoryAdapter(client=client, agent_id="reviewer_1", agent_role="reviewer")
    wrapped_node = graph_adapter.wrap_node(
        lambda state: {**state, "message": "Reviewer checked the retry implementation."}
    )
    graph_result = wrapped_node({"task_id": "task_sdk_demo", "query": "retry approval"})
    print("graph trace:", graph_result["memory_trace_id"])


if __name__ == "__main__":
    main()
