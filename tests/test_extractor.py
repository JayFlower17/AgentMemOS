from agentmemos.enums import AgentRole, EventType, MemoryScope, MemoryType
from agentmemos.extractor import (
    RuleBasedExtractor,
    create_extractor_provider,
    detect_content_signals,
    explain_extraction,
    extract_memory,
)
from agentmemos.models import AgentEventModel


def make_event(event_type: EventType, role: AgentRole, content: str) -> AgentEventModel:
    return AgentEventModel(
        event_id="evt_extractor_test",
        event_type=event_type,
        task_id="task_extractor_test",
        agent_id=f"{role}_1",
        agent_role=role,
        content=content,
        event_metadata={},
    )


def test_review_finding_extracts_team_shared_episodic_memory_with_signals():
    event = make_event(
        EventType.review_finding_created,
        AgentRole.reviewer,
        "The reviewer found that retries need bounded backoff before approval.",
    )

    memory = extract_memory(event)
    assert memory is not None
    assert memory.memory_type == MemoryType.episodic
    assert memory.scope == MemoryScope.team_shared
    assert memory.importance >= 0.9

    reason, signals = explain_extraction(event, memory)
    assert "Review findings" in reason
    assert signals["decision_signal"] is True
    assert signals["extractor"] == "structured-rule-v2"
    assert "event:review_finding" in signals["applied_rules"]


def test_completed_task_with_procedural_language_extracts_reusable_team_guidance():
    event = make_event(
        EventType.task_completed,
        AgentRole.planner,
        "When demoing AgentMemOS, seed extracted events before opening the dashboard.",
    )

    memory = extract_memory(event)
    assert memory is not None
    assert memory.memory_type == MemoryType.procedural
    assert memory.scope == MemoryScope.team_shared
    assert memory.importance >= 0.86

    _, signals = explain_extraction(event, memory)
    assert signals["procedure_signal"] is True
    assert "content:procedure" in signals["applied_rules"]


def test_coder_scratch_tool_observation_stays_agent_local():
    event = make_event(
        EventType.tool_result_observed,
        AgentRole.coder,
        "Temporary scratch: pytest failed because the retry timeout exceeded the limit.",
    )

    memory = extract_memory(event)
    assert memory is not None
    assert memory.memory_type == MemoryType.episodic
    assert memory.scope == MemoryScope.agent_local
    assert memory.importance > 0.65

    _, signals = explain_extraction(event, memory)
    assert signals["scratch_signal"] is True
    assert signals["failure_signal"] is True
    assert "content:risk_or_failure" in signals["applied_rules"]


def test_content_signal_detection_supports_chinese_project_notes():
    signals = detect_content_signals("必须先处理冲突，否则会出现失败风险。")
    assert signals["procedure_signal"] is True
    assert signals["risk_signal"] is True
    assert signals["failure_signal"] is True


def test_rule_based_extractor_returns_structured_result():
    event = make_event(
        EventType.review_finding_created,
        AgentRole.reviewer,
        "The reviewer found that retries need bounded backoff before approval.",
    )

    result = RuleBasedExtractor().extract(event)

    assert result.should_write is True
    assert result.memory is not None
    assert result.memory.memory_type == MemoryType.episodic
    assert result.reason.startswith("Review findings")
    assert result.provider == "rule"
    assert result.signals["extractor"] == "structured-rule-v2"
    assert "event:review_finding" in result.signals["applied_rules"]


def test_rule_based_extractor_skips_empty_content_with_auditable_reason():
    event = make_event(EventType.agent_message_sent, AgentRole.coder, "   ")

    result = RuleBasedExtractor().extract(event)

    assert result.should_write is False
    assert result.memory is None
    assert "Empty event content" in result.reason
    assert "content:empty" in result.signals["applied_rules"]


def test_extractor_provider_factory_defaults_to_rule_backend():
    provider = create_extractor_provider()

    assert isinstance(provider, RuleBasedExtractor)
