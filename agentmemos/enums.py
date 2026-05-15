from enum import StrEnum


class AgentRole(StrEnum):
    planner = "planner"
    coder = "coder"
    reviewer = "reviewer"
    user = "user"
    assistant = "assistant"


class EventType(StrEnum):
    task_created = "task.created"
    task_claimed = "task.claimed"
    agent_message_sent = "agent.message.sent"
    conversation_turn_observed = "conversation.turn.observed"
    tool_result_observed = "tool.result.observed"
    subtask_completed = "subtask.completed"
    review_finding_created = "review.finding.created"
    task_completed = "task.completed"


class MemoryScope(StrEnum):
    agent_local = "agent-local"
    task_local = "task-local"
    team_shared = "team-shared"
    project_global = "project-global"


class MemoryType(StrEnum):
    working = "working"
    episodic = "episodic"
    procedural = "procedural"


class MemoryStatus(StrEnum):
    active = "active"
    superseded = "superseded"
    archived = "archived"
