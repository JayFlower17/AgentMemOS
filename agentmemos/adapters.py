from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agentmemos.sdk import AgentMemOSClient


AgentState = dict[str, Any]
AgentStep = Callable[[AgentState], AgentState]
QueryBuilder = Callable[[AgentState], str]
ContentBuilder = Callable[[AgentState, AgentState], str]


def default_query_builder(state: AgentState) -> str:
    return str(
        state.get("current_goal")
        or state.get("query")
        or state.get("task")
        or state.get("task_id")
        or ""
    )


def default_content_builder(before: AgentState, after: AgentState) -> str:
    if "result" in after:
        return str(after["result"])
    if "output" in after:
        return str(after["output"])
    if "message" in after:
        return str(after["message"])
    return f"Agent step completed for task {after.get('task_id', before.get('task_id', 'unknown'))}."


@dataclass(frozen=True)
class MemoryStepAdapter:
    """Wrap a framework-agnostic agent step with AgentMemOS retrieval and event emission."""

    client: AgentMemOSClient
    agent_id: str
    agent_role: str
    memory_context_key: str = "memory_context"
    event_type: str = "subtask.completed"
    allowed_scopes: list[str] | None = None
    query_builder: QueryBuilder = default_query_builder
    content_builder: ContentBuilder = default_content_builder

    def wrap(self, step: AgentStep) -> AgentStep:
        def wrapped(state: AgentState) -> AgentState:
            task_id = self._require(state, "task_id")
            query = self.query_builder(state)
            retrieval = self.client.retrieve(
                task_id=task_id,
                agent_id=self.agent_id,
                agent_role=self.agent_role,
                query=query,
                allowed_scopes=self.allowed_scopes,
            )

            next_state = dict(state)
            next_state[self.memory_context_key] = retrieval.get("packed_context", "")
            next_state["memory_trace_id"] = retrieval.get("trace_id")

            result_state = step(next_state)
            if result_state is None:
                result_state = next_state

            self.client.emit_event(
                event_type=self.event_type,
                task_id=task_id,
                agent_id=self.agent_id,
                agent_role=self.agent_role,
                content=self.content_builder(next_state, result_state),
                metadata={
                    "memory_trace_id": retrieval.get("trace_id"),
                    "adapter": "MemoryStepAdapter",
                },
            )
            return result_state

        return wrapped

    @staticmethod
    def _require(state: AgentState, key: str) -> str:
        value = state.get(key)
        if not value:
            raise ValueError(f"Agent state must include {key!r}")
        return str(value)


def with_agentmemos(step: AgentStep, **kwargs: Any) -> AgentStep:
    return MemoryStepAdapter(**kwargs).wrap(step)
